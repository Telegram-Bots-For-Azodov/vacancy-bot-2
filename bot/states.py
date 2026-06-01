from aiogram.fsm.state import State, StatesGroup


class TokenStates(StatesGroup):
    waiting_token = State()
