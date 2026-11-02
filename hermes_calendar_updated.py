#!/usr/bin/env python3
"""
Modulo Oficial de Integracao Google Calendar do Hermes Agent via Service Account
Agenda: Agenda Hermes (suporteninja1@gmail.com)
Fuso Horario: America/Sao_Paulo (UTC-3)
"""

import sys
import os

# Garantir acesso aos pacotes instalados no venv do Hermes independente do python chamado
for p in [
    "/opt/hermes/.venv/lib/python3.14/site-packages",
    "/opt/hermes/.venv/lib/python3.13/site-packages",
    "/opt/hermes/.venv/lib/python3.12/site-packages",
    "/opt/hermes/.venv/lib/python3.11/site-packages",
]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

import json
import re
import unicodedata
import datetime
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
DEFAULT_KEY_FILE = os.getenv('HERMES_GOOGLE_KEY', '/opt/data/service_account.json')
CALENDAR_ID = os.getenv('HERMES_CALENDAR_ID', 'suporteninja1@gmail.com')
TZ_SP = ZoneInfo('America/Sao_Paulo')

def normalize_text(text):
    if not text:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(text).lower())
        if unicodedata.category(c) != 'Mn'
    ).strip()

def get_calendar_service(key_file=DEFAULT_KEY_FILE):
    if not os.path.exists(key_file):
        raise FileNotFoundError(f'Chave da conta de servico nao encontrada em: {key_file}')
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def parse_datetime(date_str, time_str='10:00'):
    now = datetime.datetime.now(TZ_SP)
    
    time_str = str(time_str).lower().replace('h', ':').replace('hrs', '').replace('hr', '').strip()
    if ':' not in time_str:
        time_str = f'{time_str}:00'
    parts = time_str.split(':')
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0

    target_date = now.date()
    d_clean = str(date_str).lower().strip()
    
    if d_clean in ['hoje', 'today', '1']:
        target_date = now.date()
    elif d_clean in ['amanha', 'amanhã', 'tomorrow']:
        target_date = now.date() + datetime.timedelta(days=1)
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', d_clean):
        target_date = datetime.date.fromisoformat(d_clean)
    elif re.match(r'^\d{2}/\d{2}/\d{4}$', d_clean):
        day, month, year = map(int, d_clean.split('/'))
        target_date = datetime.date(year, month, day)
    elif re.match(r'^\d{2}/\d{2}$', d_clean):
        day, month = map(int, d_clean.split('/'))
        target_date = datetime.date(now.year, month, day)

    target_dt = datetime.datetime(
        target_date.year, target_date.month, target_date.day,
        hour, minute, 0, tzinfo=TZ_SP
    )
    return target_dt

def list_upcoming_events(days=7, filter_mode=None):
    service = get_calendar_service()
    now = datetime.datetime.now(TZ_SP)
    
    if filter_mode in ['hoje', 'today']:
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif filter_mode in ['amanha', 'amanhã', 'tomorrow']:
        tom = now + datetime.timedelta(days=1)
        time_min = tom.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = tom.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Default: a partir do inicio de hoje ate N dias
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = (now + datetime.timedelta(days=days)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        maxResults=50,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    res = []
    for ev in events:
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        end = ev['end'].get('dateTime', ev['end'].get('date'))
        res.append({
            'id': ev['id'],
            'summary': ev.get('summary', 'Sem titulo'),
            'description': ev.get('description', ''),
            'start': start,
            'end': end,
            'htmlLink': ev.get('htmlLink', ''),
        })
    return res

def check_conflict(start_dt, end_dt, ignore_event_id=None):
    service = get_calendar_service()
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=(start_dt - datetime.timedelta(hours=2)).isoformat(),
        timeMax=(end_dt + datetime.timedelta(hours=2)).isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    for ev in events_result.get('items', []):
        if ignore_event_id and ev['id'] == ignore_event_id:
            continue
        s_raw = ev['start'].get('dateTime')
        e_raw = ev['end'].get('dateTime')
        if not s_raw or not e_raw:
            continue
        ev_start = datetime.datetime.fromisoformat(s_raw.replace('Z', '+00:00'))
        ev_end = datetime.datetime.fromisoformat(e_raw.replace('Z', '+00:00'))
        
        # Conflito se o novo evento sobrepoe o existente
        if start_dt < ev_end and end_dt > ev_start:
            return {
                'id': ev['id'],
                'summary': ev.get('summary', 'Sem titulo'),
                'start': ev_start.strftime('%H:%M'),
                'end': ev_end.strftime('%H:%M'),
                'date': ev_start.strftime('%d/%m/%Y')
            }
    return None

def create_event(summary, start_dt, duration_minutes=60, description='', attendee_email=None, force=False):
    service = get_calendar_service()
    
    if isinstance(start_dt, str):
        if 't' in start_dt.lower():
            start_dt = datetime.datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
        else:
            start_dt = parse_datetime('hoje', start_dt)
            
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
    
    if not force:
        conflict = check_conflict(start_dt, end_dt)
        if conflict:
            return {
                'conflict': True,
                'message': f"CONFLITO DETECTADO: Voce ja possui o compromisso '{conflict['summary']}' no dia {conflict['date']} das {conflict['start']} as {conflict['end']}!",
                'conflict_event': conflict
            }
            
    body = {
        'summary': summary,
        'description': description or 'Agendado pelo Hermes Agent.',
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Sao_Paulo'},
    }
    
    if attendee_email:
        body['attendees'] = [{'email': attendee_email}]
        
    event = service.events().insert(
        calendarId=CALENDAR_ID,
        body=body,
        sendUpdates='all' if attendee_email else 'none'
    ).execute()
    
    return {
        'conflict': False,
        'id': event['id'],
        'summary': event['summary'],
        'start': event['start'].get('dateTime'),
        'end': event['end'].get('dateTime'),
        'htmlLink': event.get('htmlLink')
    }

def find_event(query, date_str=None, time_str=None):
    service = get_calendar_service()
    
    # 1. Se query e um ID alfanumerico direto (sem espacos e len > 15)
    clean_q = str(query).strip()
    if re.match(r'^[a-z0-9_]{10,64}$', clean_q):
        try:
            ev = service.events().get(calendarId=CALENDAR_ID, eventId=clean_q).execute()
            if ev and ev.get('status') != 'cancelled':
                start = ev['start'].get('dateTime', ev['start'].get('date'))
                end = ev['end'].get('dateTime', ev['end'].get('date'))
                return {
                    'id': ev['id'],
                    'summary': ev.get('summary', 'Sem titulo'),
                    'start': start,
                    'end': end,
                    'htmlLink': ev.get('htmlLink', '')
                }
        except Exception:
            pass

    # 2. Busca nos proximos 30 dias por titulo e/ou horario
    norm_query = normalize_text(query)
    clean_time = time_str.replace('h', ':').strip() if time_str else ''
    
    events = list_upcoming_events(days=30)
    
    candidates = []
    for ev in events:
        norm_summary = normalize_text(ev['summary'])
        start_str = ev['start']
        
        # Filtro de data se fornecido
        if date_str:
            norm_date = normalize_text(date_str)
            if 'hoje' in norm_date:
                today_iso = datetime.datetime.now(TZ_SP).strftime('%Y-%m-%d')
                if not start_str.startswith(today_iso):
                    continue
            elif 'amanha' in norm_date:
                tom_iso = (datetime.datetime.now(TZ_SP) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                if not start_str.startswith(tom_iso):
                    continue
                    
        # Match no titulo ou no horario
        title_match = norm_query in norm_summary or norm_summary in norm_query
        time_match = False
        if clean_time and 'T' in start_str:
            time_part = start_str.split('T')[1][:5]
            if clean_time in time_part or time_part in clean_time:
                time_match = True
                
        if title_match and time_match:
            return ev  # Match perfeito de titulo + horario
        elif title_match:
            candidates.append((2, ev))
        elif time_match and norm_query in ['evento', 'agenda', 'compromisso', 'reuniao', 'reunião', '']:
            candidates.append((1, ev))
            
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
        
    return None

def smart_delete(query, time_str=None, date_str=None):
    service = get_calendar_service()
    
    target = find_event(query, date_str=date_str, time_str=time_str)
    if not target:
        return {
            'success': False,
            'message': f"Nenhum compromisso correspondente a '{query}' foi localizado para exclusao."
        }
        
    service.events().delete(calendarId=CALENDAR_ID, eventId=target['id']).execute()
    return {
        'success': True,
        'deleted_event': target,
        'message': f"Compromisso '{target['summary']}' ({target['start'][:16].replace('T', ' as ')}) removido com sucesso da Agenda Google!"
    }

def smart_move(query, new_time, date_str=None, old_time=None, duration_min=None, force=False):
    service = get_calendar_service()
    
    target = find_event(query, date_str=date_str, time_str=old_time)
    if not target:
        return {
            'success': False,
            'message': f"Nenhum compromisso correspondente a '{query}' foi localizado para alteracao."
        }
        
    old_start_str = target['start']
    old_end_str = target['end']
    
    # Calcular duracao
    if duration_min:
        dur = int(duration_min)
    elif 'T' in old_start_str and 'T' in old_end_str:
        s_dt = datetime.datetime.fromisoformat(old_start_str.replace('Z', '+00:00'))
        e_dt = datetime.datetime.fromisoformat(old_end_str.replace('Z', '+00:00'))
        dur = int((e_dt - s_dt).total_seconds() / 60)
        if dur <= 0:
            dur = 60
    else:
        dur = 60
        
    target_date_str = date_str or ("hoje" if 'T' in old_start_str and old_start_str.startswith(datetime.datetime.now(TZ_SP).strftime('%Y-%m-%d')) else old_start_str[:10])
    new_start_dt = parse_datetime(target_date_str, new_time)
    new_end_dt = new_start_dt + datetime.timedelta(minutes=dur)
    
    if not force:
        conflict = check_conflict(new_start_dt, new_end_dt, ignore_event_id=target['id'])
        if conflict:
            return {
                'success': False,
                'conflict': True,
                'message': f"CONFLITO DETECTADO: Voce ja possui o compromisso '{conflict['summary']}' no dia {conflict['date']} das {conflict['start']} as {conflict['end']}!"
            }
            
    updated_event = service.events().patch(
        calendarId=CALENDAR_ID,
        eventId=target['id'],
        body={
            'start': {'dateTime': new_start_dt.isoformat(), 'timeZone': 'America/Sao_Paulo'},
            'end': {'dateTime': new_end_dt.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        }
    ).execute()
    
    return {
        'success': True,
        'conflict': False,
        'event': {
            'id': updated_event['id'],
            'summary': updated_event.get('summary', target['summary']),
            'start': updated_event['start'].get('dateTime'),
            'end': updated_event['end'].get('dateTime'),
            'htmlLink': updated_event.get('htmlLink')
        },
        'message': f"Compromisso '{target['summary']}' alterado com sucesso para as {new_time} ({target_date_str})!"
    }

def format_event_line(e, now):
    st = e['start']
    et = e['end']
    eid = e['id']
    
    if 'T' in st:
        ev_start_dt = datetime.datetime.fromisoformat(st.replace('Z', '+00:00'))
        ev_end_dt = datetime.datetime.fromisoformat(et.replace('Z', '+00:00')) if 'T' in et else None
        
        if ev_start_dt.date() == now.date():
            dia_label = 'Hoje'
        elif ev_start_dt.date() == (now.date() + datetime.timedelta(days=1)):
            dia_label = 'Amanha'
        else:
            dia_label = ev_start_dt.strftime('%d/%m (%a)')
            
        h_start = ev_start_dt.strftime('%H:%M')
        h_end = ev_end_dt.strftime('%H:%M') if ev_end_dt else ''
        horario = f'{h_start} as {h_end}' if h_end else h_start
        return f" * [{dia_label} das {horario}] {e['summary']} (ID: {eid}) -> {e['htmlLink']}"
    else:
        return f" * [Dia todo {st}] {e['summary']} (ID: {eid}) -> {e['htmlLink']}"

if __name__ == '__main__':
    now = datetime.datetime.now(TZ_SP)
    
    if len(sys.argv) < 2 or sys.argv[1] == 'list':
        arg = sys.argv[2].lower() if len(sys.argv) > 2 else ''
        
        filter_mode = None
        days = 7
        
        if arg in ['hoje', 'today']:
            filter_mode = 'hoje'
            label = 'hoje'
        elif arg in ['amanha', 'amanhã', 'tomorrow']:
            filter_mode = 'amanha'
            label = 'amanha'
        elif arg in ['1', 'dia']:
            filter_mode = 'hoje'
            label = 'hoje'
        elif arg in ['semana', '7']:
            days = 7
            label = 'proximos 7 dias'
        elif arg in ['mes', 'mês', '30']:
            days = 30
            label = 'proximos 30 dias'
        elif arg.isdigit():
            days = int(arg)
            label = f'proximos {days} dias'
        else:
            days = 7
            label = 'proximos 7 dias'
            
        evs = list_upcoming_events(days=days, filter_mode=filter_mode)
        if not evs:
            print(f'Nenhum compromisso agendado para {label} na Agenda Google ({CALENDAR_ID}).')
        else:
            print(f'Agenda Google ({len(evs)} compromisso(s) para {label}):')
            for e in evs:
                print(format_event_line(e, now))
                
    elif sys.argv[1] in ['add', 'create']:
        if len(sys.argv) < 3:
            print("Erro: Informe o titulo do evento. Ex: agenda add 'Reuniao' '10:00' hoje")
            sys.exit(1)
        summary = sys.argv[2]
        time_arg = sys.argv[3] if len(sys.argv) > 3 else '10:00'
        date_arg = sys.argv[4] if len(sys.argv) > 4 else 'hoje'
        dur_arg = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].isdigit() else 60
        force_flag = '--force' in sys.argv
        
        dt = parse_datetime(date_arg, time_arg)
        ev = create_event(summary, dt, duration_minutes=dur_arg, force=force_flag)
        if ev.get('conflict'):
            print(f"ERRO DE CONFLITO: {ev['message']}")
            sys.exit(2)
        else:
            print(f"SUCESSO: Evento agendado na Agenda Google ({CALENDAR_ID})!")
            print(f"Titulo: {ev['summary']}")
            print(f"Inicio: {ev['start']}")
            print(f"Termino: {ev['end']}")
            print(f"Link: {ev['htmlLink']}")
            
    elif sys.argv[1] in ['del', 'delete', 'remove', 'rm']:
        if len(sys.argv) < 3:
            print("Erro: Informe o ID ou o Titulo do evento a excluir. Ex: agenda del 'Café da Manhã' 08:00 hoje")
            sys.exit(1)
        q = sys.argv[2]
        time_opt = sys.argv[3] if len(sys.argv) > 3 and ':' in sys.argv[3] else None
        date_opt = sys.argv[4] if len(sys.argv) > 4 else (sys.argv[3] if len(sys.argv) > 3 and ':' not in sys.argv[3] else 'hoje')
        
        res = smart_delete(q, time_str=time_opt, date_str=date_opt)
        if res['success']:
            print(f"SUCESSO: {res['message']}")
        else:
            print(f"ERRO: {res['message']}")
            sys.exit(1)
            
    elif sys.argv[1] in ['move', 'mudar', 'update', 'reagendar']:
        if len(sys.argv) < 4:
            print("Erro: Uso: agenda move '<Titulo ou ID>' '<Novo_Horario>' [hoje|amanha] [duracao_min]")
            sys.exit(1)
        q = sys.argv[2]
        new_time = sys.argv[3]
        date_opt = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].isdigit() else 'hoje'
        dur_opt = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5].isdigit() else (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4].isdigit() else None)
        force_flag = '--force' in sys.argv
        
        res = smart_move(q, new_time, date_str=date_opt, duration_min=dur_opt, force=force_flag)
        if res['success']:
            print(f"SUCESSO: {res['message']}")
            print(f"Novo Horario: {res['event']['start']}")
            print(f"Link: {res['event']['htmlLink']}")
        else:
            print(f"ERRO: {res['message']}")
            sys.exit(2 if res.get('conflict') else 1)
