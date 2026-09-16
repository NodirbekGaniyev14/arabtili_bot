"""Telegram Payments (Payme/Click) update'lari — K18.5, services/payments.py.

`pre_checkout_query` ga 10 soniya ichida javob berish shart — tekshiruv faqat
payload/summa/foydalanuvchi (tarmoqqa chiqilmaydi). `successful_payment`
kelganda VIP beriladi; takror update (bir xil charge_id) e'tiborsiz qoladi.
"""

from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery

from db.session import SessionLocal
from services import payments

router = Router()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot):
    async with SessionLocal() as session:
        error = await payments.validate(
            session, query.from_user.id, query.invoice_payload, query.currency, query.total_amount
        )
    if error:
        await query.answer(ok=False, error_message=error)
    else:
        await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    if message.from_user is None or message.successful_payment is None:
        return
    async with SessionLocal() as session:
        await payments.on_success(session, bot, message.from_user.id, message.successful_payment)
