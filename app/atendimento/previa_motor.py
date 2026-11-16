"""Sugestoes locais do motor. Banco em memoria, sem alertas e sem IA."""
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from ..database import Base
from . import motor, ponte_whatsapp

class PreviaMotor:
    def __init__(self, contato, nome):
        self.contato = ponte_whatsapp.normalizar_contato(contato)
        self.nome = nome.strip()
        if not self.nome:
            raise ValueError('Nome de teste obrigatorio.')
        ponte_whatsapp._sem_ia()
        motor.notificar = lambda *args, **kwargs: None
        self.engine = create_engine('sqlite://', poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)
        self.conversa_id = None
        self.pausada = False

    def processar(self, nome, direcao, texto):
        if nome != self.nome or direcao != 'entrada' or self.pausada:
            return
        texto = texto.strip()
        if not texto or len(texto) > 4000:
            print('PREVIA: texto vazio ou acima de 4000 caracteres; ignorado.', flush=True)
            return
        with self.session() as db:
            if self.conversa_id is None:
                conv = motor.criar_conversa(db, self.contato, self.nome, canal='previa_local')
                self.conversa_id = conv.id
            else:
                conv = db.get(motor.Conversa, self.conversa_id)
            if conv.estado in (motor.ESTADO_AGUARDANDO, motor.ESTADO_HUMANO, motor.ESTADO_ENCERRADA):
                print('PREVIA: fluxo parado para humano/encerrado. Nenhum atendente foi notificado. Reinicie para novo teste.', flush=True)
                return
            novas = motor.processar_mensagem_cliente(db, conv, texto=texto)
            respostas = [m.texto for m in novas if m.autor == 'ia' and m.texto]
            if any(re.search(r'foto|print|imagem|v[ií]deo|[aá]udio', r, re.I) for r in respostas):
                motor.transferir(db, conv, 'Verificacao humana necessaria; pedidos de midia bloqueados', aviso='')
                db.commit()
                respostas = ['Este caso precisa de verificacao humana. Continue somente por texto.']
            print('PREVIA DO MOTOR - NAO ENVIADA:', flush=True)
            for resposta in respostas:
                print(resposta.replace('[[TRANSFERIR]]', '').strip(), flush=True)
            if not respostas:
                print('(sem resposta)', flush=True)
            print('SIMULACAO | estado=' + conv.estado + ' | etapa=' + conv.etapa, flush=True)
            if conv.estado in (motor.ESTADO_AGUARDANDO, motor.ESTADO_HUMANO):
                print('Transferencia apenas simulada; nenhum alerta externo foi enviado.', flush=True)

    def pausar(self):
        if not self.pausada:
            self.pausada = True
            print('PREVIA PAUSADA: houve troca de conversa ou mensagem propria. Reinicie para novo teste.', flush=True)

    def close(self):
        self.engine.dispose()
