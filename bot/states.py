from aiogram.fsm.state import State, StatesGroup


class TokenStates(StatesGroup):
    waiting_token = State()


class BroadcastStates(StatesGroup):
    waiting_content = State()
    confirm = State()


class AdminMgmtStates(StatesGroup):
    waiting_add = State()
