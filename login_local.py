from pathlib import Path
import hashlib, secrets, sqlite3, time, hmac, html, getpass
from urllib.parse import parse_qs
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import API_KEY

ROOT = Path(__file__).resolve().parent
STORE = ROOT / '.local-auth' / 'login.sqlite3'
COOKIE = 'connecttv_session'
ORIGIN = 'http://127.0.0.1:8033'
TTL = 8 * 3600

def connect():
    if not STORE.is_file():
        raise RuntimeError('Cadastre o administrador: python login_local.py cadastrar')
    return sqlite3.connect(STORE)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000)

def cadastrar():
    STORE.parent.mkdir(parents=True, exist_ok=True)
    if STORE.exists():
        raise SystemExit('Cadastro ja existe. Nenhuma senha foi substituida.')
    user = input('Usuario administrador: ').strip()
    if not user or len(user) > 80:
        raise SystemExit('Usuario invalido.')
    password = getpass.getpass('Senha (minimo 6 caracteres; pode usar uma frase): ')
    if len(password) < 6 or len(password) > 256:
        raise SystemExit('Use entre 6 e 256 caracteres.')
    if password != getpass.getpass('Repita a senha: '):
        raise SystemExit('Senhas diferentes. Execute novamente.')
    salt = secrets.token_bytes(16)
    encoded = password_hash(password, salt)
    with sqlite3.connect(STORE) as db:
        db.executescript('CREATE TABLE admin (usuario TEXT PRIMARY KEY, salt BLOB, hash BLOB); CREATE TABLE sessoes (token TEXT PRIMARY KEY, expira REAL); CREATE TABLE tentativas (id INTEGER PRIMARY KEY CHECK(id=1), falhas INTEGER, bloqueado REAL); INSERT INTO tentativas VALUES(1,0,0);')
        db.execute('INSERT INTO admin VALUES(?,?,?)', (user,salt,encoded))
    print('Administrador cadastrado. Senha nao exibida nem armazenada em texto puro.')

def page(content):
    return HTMLResponse('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ConnectTV - Acesso</title><style>body{margin:0;background:#100d26;color:#eef0ff;font:16px system-ui;display:grid;min-height:100vh;place-items:center}main{background:#211a43;border:1px solid #ffffff25;border-radius:18px;padding:30px;width:min(370px,82vw)}label{display:block;margin-top:16px}input,button{box-sizing:border-box;width:100%;padding:12px;margin-top:8px;border-radius:9px;border:1px solid #ffffff30;background:#15102c;color:white;font:inherit}button{background:#7557dc;cursor:pointer}a{color:#c7b9ff}.erro{color:#ffb0b0}</style><main><h1>ConnectTV</h1>'+content+'</main></html>', headers={'Cache-Control':'no-store','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','X-Content-Type-Options':'nosniff'})

def login_page(message=''):
    csrf = secrets.token_urlsafe(32)
    response = page('<h2>Acessar o sistema</h2><p class="erro">'+html.escape(message)+'</p><form method="post" action="/login"><input type="hidden" name="csrf" value="'+csrf+'"><label>Usuario<input name="usuario" autocomplete="username" maxlength="80" required></label><label>Senha<input name="senha" type="password" autocomplete="current-password" maxlength="256" required></label><button>Entrar</button></form>')
    response.set_cookie('connecttv_login_csrf',csrf,httponly=True,samesite='strict',max_age=600,path='/login')
    return response

def valid_session(request):
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>200:return False
    with connect() as db:
        return db.execute('SELECT 1 FROM sessoes WHERE token=? AND expira>?',(digest(token),time.time())).fetchone() is not None

class LoginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        if request.headers.get('host','') != '127.0.0.1:8033':
            return JSONResponse({'detail':'Use http://127.0.0.1:8033'},status_code=400)
        path=request.url.path
        # Credencial de servico restrita as chamadas da ponte conhecida.
        service_route=(request.method=='GET' and path=='/atendimento/config') or (request.method=='GET' and path.startswith('/whatsapp/status/')) or (request.method=='POST' and path=='/whatsapp/receber')
        supplied=request.headers.get('x-api-key','')
        service=bool(API_KEY and supplied and hmac.compare_digest(supplied,API_KEY)) and service_route
        if path=='/login':
            if request.method=='GET':return login_page()
            if request.method!='POST':return JSONResponse({'detail':'Metodo nao permitido'},status_code=405)
            if request.headers.get('origin')!=ORIGIN:return JSONResponse({'detail':'Origem invalida'},status_code=403)
            if int(request.headers.get('content-length','0') or '0')>4096:return JSONResponse({'detail':'Formulario muito grande'},status_code=413)
            raw=await request.body()
            if len(raw)>4096:return JSONResponse({'detail':'Formulario muito grande'},status_code=413)
            fields=parse_qs(raw.decode('utf-8',errors='replace'))
            field=lambda key:fields.get(key,[''])[0]
            csrf=request.cookies.get('connecttv_login_csrf','')
            if not csrf or not hmac.compare_digest(csrf,field('csrf')):return login_page('Formulario expirado. Tente novamente.')
            now=time.time()
            with connect() as db:
                fails,blocked=db.execute('SELECT falhas,bloqueado FROM tentativas WHERE id=1').fetchone()
                if blocked>now:
                    response=login_page('Muitas tentativas. Aguarde ate 5 minutos.')
                    response.status_code=429
                    return response
                if blocked and blocked<=now:fails=0
                user,salt,expected=db.execute('SELECT usuario,salt,hash FROM admin').fetchone()
                candidate=field('senha')
                ok=len(candidate)<=256 and hmac.compare_digest(password_hash(candidate,salt),expected) and hmac.compare_digest(field('usuario').encode(),user.encode())
                if not ok:
                    fails+=1
                    db.execute('UPDATE tentativas SET falhas=?,bloqueado=? WHERE id=1',(fails,now+300 if fails>=5 else 0))
                    return login_page('Usuario ou senha invalidos.')
                db.execute('UPDATE tentativas SET falhas=0,bloqueado=0 WHERE id=1')
                db.execute('DELETE FROM sessoes WHERE expira<=?',(now,))
                token=secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessoes VALUES(?,?)',(digest(token),now+TTL))
            response=RedirectResponse('/painel',status_code=303)
            response.set_cookie(COOKIE,token,httponly=True,samesite='strict',max_age=TTL,path='/')
            response.delete_cookie('connecttv_login_csrf',path='/login')
            response.headers['Cache-Control']='no-store'
            return response
        signed=valid_session(request)
        if not signed and not service:
            if request.method=='GET' and ('text/html' in request.headers.get('accept','') or path in ('/','/painel','/atendimento','/indicadores','/docs','/redoc','/conta')):
                return RedirectResponse('/login',status_code=303)
            return JSONResponse({'detail':'Login necessario'},status_code=401,headers={'Cache-Control':'no-store'})
        if signed and not service and request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('origin')!=ORIGIN:
                return JSONResponse({'detail':'Origem invalida'},status_code=403)
        if path=='/logout':
            if request.method!='POST':return page('<h2>Sair do sistema</h2><form method="post" action="/logout"><button>Confirmar saida</button></form><p><a href="/painel">Voltar</a></p>')
            with connect() as db:db.execute('DELETE FROM sessoes WHERE token=?',(digest(request.cookies.get(COOKIE,'')),))
            response=RedirectResponse('/login',status_code=303)
            response.delete_cookie(COOKIE,path='/')
            response.headers['Cache-Control']='no-store'
            return response
        if signed and not service:
            request.scope['headers']=[(k,v) for k,v in request.scope['headers'] if k.lower()!=b'x-api-key']+[(b'x-api-key',API_KEY.encode())]
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Frame-Options']='DENY'
        response.headers['X-Content-Type-Options']='nosniff'
        if signed and request.method=='GET' and response.status_code==200 and 'text/html' in response.headers.get('content-type','') and path in ('/painel','/atendimento','/indicadores'):
            body=b''.join([chunk async for chunk in response.body_iterator])
            extra=b'<a href="/logout" style="position:fixed;bottom:16px;right:18px;z-index:9999;background:#332750;color:white;border:1px solid #ffffff40;padding:10px 16px;border-radius:10px;text-decoration:none;font:14px system-ui">Sair do sistema</a>'
            body=body.replace(b'</head>', b'<script id="connecttv-session-bridge">(function(){localStorage.setItem(\'assinaturas.apiKey\',\'sessao-local\');const originalFetch=window.fetch.bind(window);window.fetch=async function(input,options){const response=await originalFetch(input,options);const raw=input instanceof Request?input.url:String(input);let same=false;try{same=new URL(raw,location.href).origin===location.origin}catch(_){}if(same&&response.status===401){location.replace(\'/login\');throw new Error(\'Sessao expirada. Entre novamente.\')}return response};document.addEventListener(\'click\',function(event){if(event.target.closest&&event.target.closest(\'#btnSair\')){event.preventDefault();event.stopImmediatePropagation();location.assign(\'/logout\')}},true)})();</script>'+b'</head>',1)
            body=body.replace(b'</body>',extra+b'</body>')
            headers=dict(response.headers)
            headers.pop('content-length',None)
            headers.pop('content-type',None)
            return HTMLResponse(body,status_code=response.status_code,headers=headers)
        return response

def proteger(app):
    with connect() as db:
        if not db.execute('SELECT 1 FROM admin').fetchone():raise RuntimeError('Administrador ausente.')
    app.add_middleware(LoginMiddleware)

if __name__=='__main__':
    import sys
    if sys.argv[1:]==['cadastrar']:cadastrar()
    else:print('Use: python login_local.py cadastrar')

