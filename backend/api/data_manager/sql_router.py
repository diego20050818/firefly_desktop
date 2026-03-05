from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger

from storage.sql.conversation_manager import ConversationManager
from storage.sql.database_manager import DatabaseManager,clear_database

class conversationFommater(BaseModel):
    sessionid:str

conv = ConversationManager()
database_manager = DatabaseManager()

sqlRouter = APIRouter(
    prefix='/database',
    tags=['database']
)

@sqlRouter.post('/clear_conversation_history')
def clear_conv_history(sessionid:conversationFommater):
    try:
        conv.clear_session(session_id=sessionid.sessionid)
        logger.success(f'clear {sessionid} conversation history success')
        return {'status':'success'}
    except Exception as e:
        logger.error(f'failed to clear {sessionid} : {e}')
        return {'statue':f'failed:{e}'}

@sqlRouter.get('/get_conversation_history')
def get_conv_history(sessionid:conversationFommater):
    try:
        history = conv.get_session_history(session_id=sessionid.sessionid)
        logger.success(f'get {sessionid.sessionid} history success')
        return {'session_id':sessionid.sessionid,'history':history,'status':'success'}
    except Exception as e:
        logger.error(f'get {sessionid.sessionid} failed:{e}')
        return {'session_id':{sessionid.sessionid},'history':None,'status':e}

@sqlRouter.post('/clear_database')
def handle_clear_database():
    try:
        clear_database()
        logger.success('clear full database success!')
        return {'status':'success'}
    except Exception as e:
        logger.error(f'failed clear database:{e}')
        return {'status':e}

