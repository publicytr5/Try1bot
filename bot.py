import logging
import random
import string
import asyncio
import os
import json
import qrcode
import urllib.request
from io import BytesIO
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import threading

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")
PORT = int(os.environ.get("PORT", 8080))

BOT_USERNAME = "vanila_card_bot"
ADMIN_ID = 8508012498
CONTACT_USERNAME = "Vanilacardprepaid"
CAD_TO_USD_RATE = 0.73

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "running", "message": "Bot is running!"})

@app.route('/health')
def health():
    return "OK", 200


# =========================================================
#  CRYPTO ADDRESSES
# =========================================================
BTC_ADDRESSES = [
    "bc1q9y9hd5n8gtntthq9ersuvhtqu6s9v7ulvegqzc",
    "bc1qp8v0zhe7kv2dzkuv5y2qsh5enqvg38tuxz79d2",
    "bc1qs06ez4amhq6t59dh9m7808e9h5aupjpu06ggwz",
    "bc1q86xcx5f04hv5x4zfw48uz8akq7jcanlag4v085",
    "bc1qu8egu9vepvhhuzual60tydwcckftexapznaxny",
    "bc1qcjn4ahwph2zzk8hfj00wjdmx47per3te9ldd5d",
    "bc1qcx8x7xvp6a4dtg9p8sg6kgrw7gd9qr2ps6pxhu",
    "bc1qs33lvrh8ds9q8r2hm606dkpkgfa8gzyc8qyq7y",
    "bc1qaa2e5xsgy4spdlar7upa06wgg6v90s94044uzs",
    "bc1qz257q9e4ralah45mdyfn5qrnm7rj02jkffwr9s",
]

SOL_ADDRESSES = [
    "6uuo46QkVAQbD6WF9rRWgaoJ9ppzFvtLaJvfZUqDhokQ",
    "7J7rnyXvKzbLz32RNfEUjb8xDB3ypg97MrMLKQgKEzga",
    "5xKTDpubwMGHUEA8vWM9ssr5ZxgZ8ZSUoGnxkf51WCxQ",
    "5PKJ5R1iErVzWo6nq8jCCkRT3BmswMJu5bpzXGoGwrmn",
    "7ea2cVE4RTJMqHFhcSWLg7giEcDuWmYi2gp2HYEEMvM9",
    "AcfS61yY8sxX48MyQx974PyUoVFCHcuamhdKRokNkTDw",
    "8zKUmv8ckC67pcVAsDL2nuBVxf565sMPmgswRfFhU8T2",
    "ZCa6puicMofi7prKzHkXUtCmrZWcTKQLsphxE9M3drJ",
    "5mT7UpoYZGQ8wcSX3Qfcd8392eeqZAnN22TDwxYxEirs",
    "C5ab5tGbEG6kSHc8T9KmZK57TQ54FSMVpML3adgEFvew",
]

LTC_ADDRESSES = [
    "ltc1q9xefn6xjnzfur6awf28f324g3lqwxv5a308khf",
    "ltc1qfxa8qdjutmj404tln8cp7p3sc377nfryzpaht8",
    "ltc1qt5qansym0lgd0dya6ytpzwjl7vrnz98faxrnpw",
    "ltc1q2jf2qv2tn2khauax38ga82w0x7vd825582kysf",
    "ltc1q65jxv9k5msl0dnfqg7s69r36ne0e7uvqm9elr6",
    "ltc1qky4fam6zde44va7df0y3np972hhaxty3twurx9",
    "ltc1q4rchgg5t6px89x7u2qvavllnn2085gl3wqfwtl",
    "ltc1qz0es44nll6eexdtmyu7qlvywuunzmz3tu5faty",
    "ltc1q3802u3xe5vnuepj4zmak400mqyvt559xn6au3e",
    "ltc1qxqdcsyfnlkxsycmjlaln3s58tt8sejtfwxxhwz",
]

COIN_META = {
    "BTC": {"label": "₿  BTC", "name": "Bitcoin",  "emoji": "₿",  "addresses": BTC_ADDRESSES, "cg_id": "bitcoin",  "fallback": 95000.0},
    "SOL": {"label": "🟣  SOL", "name": "Solana",   "emoji": "🟣", "addresses": SOL_ADDRESSES, "cg_id": "solana",   "fallback": 200.0},
    "LTC": {"label": "🪙 LTC", "name": "Litecoin", "emoji": "🪙", "addresses": LTC_ADDRESSES, "cg_id": "litecoin", "fallback": 71.17},
}


def fetch_crypto_rate_usd_sync(coin_symbol: str) -> float:
    """CoinGecko থেকে লাইভ USD রেট আনে, ব্যর্থ হলে fallback দেয়।"""
    meta = COIN_META.get(coin_symbol.upper())
    if not meta:
        return 0.0
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={meta['cg_id']}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return float(data[meta["cg_id"]]["usd"])
    except Exception as e:
        logger.error(f"Rate fetch failed for {coin_symbol}: {e}")
        return float(meta["fallback"])


# =========================================================
#  CARDS & BINS
# =========================================================
CARD_BINS = {
    "USD": ["435880xx", "491277xx", "511332xx", "428313xx", "520356xx", "409758xx",
            "525362xx", "451129xx", "434340xx", "426370xx", "411810xx", "403446xx",
            "533621xx", "446317xx", "457824xx", "545660xx", "432465xx", "516612xx",
            "484718xx", "485246xx", "402372xx", "457851xx"],
    "CAD": ["533985xx", "461126xx"],
    "AUD": ["373778xx", "377935xx", "375163xx"]
}
CAD_BINS = ["533985xx", "461126xx"]
AUD_BINS = ["373778xx", "377935xx", "375163xx"]

FILTER_BIN_MAP = {
    "vanilla":      ["411810xx", "409758xx", "520356xx", "525362xx", "484718xx", "545660xx"],
    "cardbalance":  ["428313xx", "432465xx", "457824xx"],
    "walmart":      ["485246xx"],
    "giftcardmall": ["451129xx", "403446xx", "435880xx", "511332xx"],
    "joker":        ["533985xx", "461126xx"],
    "amex":         ["373778xx", "377935xx", "375163xx"]
}


class StickerType(Enum):
    NONE = ""
    RELISTED = "🔄"
    GOOGLE = "🅶"
    PAYPAL = "🅿"


@dataclass
class Card:
    card_number: str
    currency: str
    amount: float
    sticker: StickerType = StickerType.NONE
    is_registered: bool = True
    is_out_of_stock: bool = False

    def display(self) -> str:
        sticker_str = f" {self.sticker.value}" if self.sticker != StickerType.NONE else ""
        return f"{self.card_number} {self.currency}${self.amount:.2f} at 35%{sticker_str}"


@dataclass
class UserData:
    user_id: int
    username: str
    first_name: str
    chat_id: int = 0
    usd_balance: float = 0.0
    total_deposits_usd: float = 0.0
    last_deposit: str = "Never"
    purchase_count: int = 0
    usd_spent: float = 0.0
    purchased_cards: List[str] = field(default_factory=list)
    referrals_count: int = 0
    referred_by: str = ""
    referral_link: str = ""
    pending_deposit: Optional[Dict] = None


class CardGenerator:
    def __init__(self):
        self.cards: List[Card] = []
        self._last_update_time = None
        self._is_updating = False

    def _generate_unique_number(self, existing_numbers: set) -> str:
        while True:
            bin_list = []
            for currency, bins in CARD_BINS.items():
                bin_list.extend(bins)
            selected_bin = random.choice(bin_list)
            random_suffix = ''.join(random.choices(string.digits, k=2))
            card_num = selected_bin.replace('xx', random_suffix)
            if card_num not in existing_numbers:
                return card_num

    def _get_max_amount_for_bin(self, card_number: str) -> float:
        bin_prefix = card_number[:6] + 'xx'
        if bin_prefix in CAD_BINS:
            return 150.0
        elif bin_prefix in AUD_BINS:
            return 50.0
        else:
            return 500.0

    def _get_sticker_for_amount(self, amount: float) -> StickerType:
        if amount >= 300:
            return StickerType.NONE
        rand = random.random()
        if rand < 0.65:
            return StickerType.NONE
        elif rand < 0.75:
            return StickerType.RELISTED
        elif rand < 0.83:
            return StickerType.GOOGLE
        elif rand < 0.87:
            return StickerType.PAYPAL
        else:
            return StickerType.GOOGLE

    def _get_currency_for_bin(self, card_number: str) -> str:
        bin_prefix = card_number[:6] + 'xx'
        for currency, bins in CARD_BINS.items():
            if bin_prefix in bins:
                return currency
        return "USD"

    def generate_cards(self) -> List[Card]:
        total_cards = random.randint(300, 350)
        cards = []
        existing_numbers = set()
        existing_pairs = set()
        low_amount_count = random.randint(15, 20)
        high_amount_count = random.randint(10, min(12, total_cards // 10))
        medium_amount_count = random.randint(20, 30)
        remaining = total_cards - (low_amount_count + high_amount_count + medium_amount_count)
        aud_count = 0
        max_aud_cards = 20

        for _ in range(low_amount_count):
            amount = round(random.uniform(0.01, 0.98), 2)
            while True:
                card_num = self._generate_unique_number(existing_numbers)
                if (card_num, amount) not in existing_pairs:
                    max_amt = self._get_max_amount_for_bin(card_num)
                    if amount <= max_amt:
                        break
            existing_numbers.add(card_num)
            existing_pairs.add((card_num, amount))
            currency = self._get_currency_for_bin(card_num)
            sticker = self._get_sticker_for_amount(amount)
            cards.append(Card(card_num, currency, amount, sticker))

        for _ in range(high_amount_count):
            amount = round(random.uniform(300, 500), 2)
            while True:
                card_num = self._generate_unique_number(existing_numbers)
                if (card_num, amount) not in existing_pairs:
                    max_amt = self._get_max_amount_for_bin(card_num)
                    if amount <= max_amt:
                        break
            existing_numbers.add(card_num)
            existing_pairs.add((card_num, amount))
            currency = self._get_currency_for_bin(card_num)
            cards.append(Card(card_num, currency, amount, StickerType.NONE))

        for _ in range(medium_amount_count):
            amount = round(random.uniform(5, 40), 2)
            while True:
                card_num = self._generate_unique_number(existing_numbers)
                if (card_num, amount) not in existing_pairs:
                    max_amt = self._get_max_amount_for_bin(card_num)
                    if amount <= max_amt:
                        if card_num[:6] + 'xx' in AUD_BINS:
                            if aud_count >= max_aud_cards:
                                continue
                        break
            existing_numbers.add(card_num)
            existing_pairs.add((card_num, amount))
            if card_num[:6] + 'xx' in AUD_BINS:
                aud_count += 1
            currency = self._get_currency_for_bin(card_num)
            sticker = self._get_sticker_for_amount(amount)
            cards.append(Card(card_num, currency, amount, sticker))

        for _ in range(remaining):
            amount = round(random.uniform(5, 40), 2)
            while True:
                card_num = self._generate_unique_number(existing_numbers)
                if (card_num, amount) not in existing_pairs:
                    max_amt = self._get_max_amount_for_bin(card_num)
                    if amount <= max_amt:
                        if card_num[:6] + 'xx' in AUD_BINS:
                            if aud_count >= max_aud_cards:
                                continue
                        break
            existing_numbers.add(card_num)
            existing_pairs.add((card_num, amount))
            if card_num[:6] + 'xx' in AUD_BINS:
                aud_count += 1
            currency = self._get_currency_for_bin(card_num)
            sticker = self._get_sticker_for_amount(amount)
            cards.append(Card(card_num, currency, amount, sticker))

        cards.sort(key=lambda x: x.amount, reverse=True)
        unregistered_count = int(len(cards) * 0.2)
        cards_by_amount_desc = sorted(cards, key=lambda x: x.amount, reverse=True)
        for i in range(unregistered_count):
            cards_by_amount_desc[len(cards_by_amount_desc) - 1 - i].is_registered = False
        return cards

    async def update_cards(self):
        self._is_updating = True
        self.cards = self.generate_cards()
        self._last_update_time = datetime.now()
        self._is_updating = False
        print(f"Cards generated: {len(self.cards)} cards")

    def mark_random_cards_out_of_stock(self, percentage: float = 1.0):
        available_cards = [c for c in self.cards if not c.is_out_of_stock]
        if not available_cards:
            return 0
        count = max(1, int(len(self.cards) * percentage / 100))
        count = min(count, len(available_cards))
        selected = random.sample(available_cards, count)
        for card in selected:
            card.is_out_of_stock = True
        print(f"Marked {count} cards as OUT OF STOCK")
        return count

    def get_cards_paginated(self, page: int, per_page: int = 10, filter_type: str = None) -> Tuple[List[Card], int]:
        if not self.cards:
            return [], 0
        filtered_cards = self.cards.copy()
        if filter_type:
            if filter_type == "unregistered":
                filtered_cards = [c for c in filtered_cards if not c.is_registered]
            elif filter_type == "registered":
                filtered_cards = [c for c in filtered_cards if c.is_registered]
            elif filter_type in FILTER_BIN_MAP:
                allowed_bins = FILTER_BIN_MAP[filter_type]
                filtered_cards = [c for c in filtered_cards
                                  if any(c.card_number.startswith(bp.replace('xx', '')) for bp in allowed_bins)]
        total_pages = max(1, (len(filtered_cards) + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        return filtered_cards[start:end], total_pages

    def get_low_amount_cards_page(self, per_page: int = 10) -> Tuple[List[Card], int]:
        if not self.cards:
            return [], 0
        low_cards = [c for c in self.cards if c.amount < 0.99]
        total_pages = max(1, (len(low_cards) + per_page - 1) // per_page)
        return low_cards, total_pages


class UserManager:
    def __init__(self):
        self.users: Dict[int, UserData] = {}
        self.order_counter = 726267

    def get_or_create_user(self, update: Update) -> UserData:
        user = update.effective_user
        chat = update.effective_chat
        if user.id not in self.users:
            referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"
            self.users[user.id] = UserData(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name,
                chat_id=chat.id if chat else 0,
                referral_link=referral_link
            )
        else:
            if chat and self.users[user.id].chat_id != chat.id:
                self.users[user.id].chat_id = chat.id
        return self.users[user.id]

    def get_next_order_number(self) -> int:
        self.order_counter += 1
        if self.order_counter > 999999:
            self.order_counter = 726267
        return self.order_counter


class KeyboardBuilder:
    @staticmethod
    def get_main_menu_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💳 Stock", callback_data="stock"),
                InlineKeyboardButton("📞 Contact Admin", url="https://t.me/Vanila_card_prepaid")
            ],
            [
                InlineKeyboardButton("Card chaker 🔍", url="https://t.me/Botcardchakerbot"),
                InlineKeyboardButton("Refund Support 🆘", url="https://t.me/vanilarefund")
            ]
        ])

    @staticmethod
    def get_filters_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 Unregistered", callback_data="filter_unregistered"),
             InlineKeyboardButton("🔓 Registered", callback_data="filter_registered")],
            [InlineKeyboardButton("⚪ Vanilla", callback_data="filter_vanilla"),
             InlineKeyboardButton("💠 CardBalance", callback_data="filter_cardbalance")],
            [InlineKeyboardButton("☀️ Walmart", callback_data="filter_walmart"),
             InlineKeyboardButton("🛍️ GiftCardMall", callback_data="filter_giftcardmall")],
            [InlineKeyboardButton("🎭 Joker", callback_data="filter_joker"),
             InlineKeyboardButton("🟦 AMEX", callback_data="filter_amex")],
            [InlineKeyboardButton("🏠 Clear Filters", callback_data="clear_filters")]
        ])

    @staticmethod
    def get_deposit_amount_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("$30", callback_data="dep_amt_30"),
             InlineKeyboardButton("$50", callback_data="dep_amt_50")],
            [InlineKeyboardButton("$100", callback_data="dep_amt_100"),
             InlineKeyboardButton("$500", callback_data="dep_amt_500")],
            [InlineKeyboardButton("✏️ Custom Amount", callback_data="dep_custom")]
        ])

    @staticmethod
    def get_coin_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("₿  BTC", callback_data="dep_coin_BTC"),
            InlineKeyboardButton("🟣  SOL", callback_data="dep_coin_SOL"),
            InlineKeyboardButton("🪙 LTC", callback_data="dep_coin_LTC"),
        ]])


card_generator = CardGenerator()
user_manager = UserManager()
keyboard_builder = KeyboardBuilder()


async def is_update_time() -> bool:
    now = datetime.now()
    return now.hour == 3 and now.minute < 10


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=job_data['message_id'])
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")


# ---------- ADMIN ----------
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text
    sent, failed = 0, 0
    for user_id, user_data in user_manager.users.items():
        if user_data.chat_id and user_data.chat_id != update.effective_chat.id:
            try:
                await context.bot.send_message(chat_id=user_data.chat_id, text=text)
                sent += 1
            except Exception as e:
                logger.error(f"Broadcast failed to {user_id}: {e}")
                failed += 1
    await update.message.reply_text(f"✅ Broadcast Done!\nSent: {sent}\nFailed: {failed}")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    if user.user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized.")
        return
    current = context.user_data.get('broadcast_mode', False)
    context.user_data['broadcast_mode'] = not current
    await update.message.reply_text("Broadcast mode ON ✅" if context.user_data['broadcast_mode'] else "Broadcast mode OFF ❌")


# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    welcome_text = (
        f"⚡️Welcome {user.first_name} to Vanila Exchange! ⚡️\n\n"
        "Sell, Buy, and strike deals in seconds!!\n"
        "All transactions are secure and transparent.\n"
        "All types of cards are available here at best rates. Current rate is 35%"
    )
    await update.message.reply_text(welcome_text, reply_markup=keyboard_builder.get_main_menu_keyboard())


# ---------- STOCK ----------
async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_update_time():
        if update.callback_query:
            await update.callback_query.answer("The bot is currently updating, please wait", show_alert=True)
        else:
            await update.message.reply_text("The bot is currently updating, please wait")
        return
    if not card_generator.cards:
        await card_generator.update_cards()
    cards, total_pages = card_generator.get_cards_paginated(1)
    if not cards:
        await update.message.reply_text("No cards available at the moment. Please try again later.")
        return
    await send_listing_page(update, context, cards, 1, total_pages)


async def send_listing_page(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            cards: List[Card], page: int, total_pages: int, filter_type: str = None):
    if not cards:
        if update.callback_query:
            await update.callback_query.edit_message_text("No cards available at the moment.")
        else:
            await update.message.reply_text("No cards available at the moment.")
        return
    user = user_manager.get_or_create_user(update)
    message_text = "Vanila Exchange - Main Listings V2\n\n"
    message_text += "Your Balance:\n"
    message_text += f"💵 USD : {user.usd_balance:.6f}\n\n"
    for i, card in enumerate(cards, 1):
        message_text += f"{i}. {card.card_number} {card.currency}${card.amount:.2f} at 35%"
        if card.sticker != StickerType.NONE:
            message_text += f" {card.sticker.value}"
        message_text += "\n"
    total_balance = sum(c.amount for c in cards)
    message_text += f"\nTotal Cards: {len(cards)} | Total Cards Balance: ${total_balance:.2f}\n"
    message_text += "Legend:\n🔄 = Re-listed\n🅶 = Used on Google\n🅿 = Used on PayPal\n\n"
    message_text += f"Filters: {filter_type or 'None'} \n"
    message_text += f"Page: {page}/{total_pages} | Updated: {datetime.now().strftime('%H:%M:%S')}"

    keyboard = []
    for i, card in enumerate(cards, 1):
        if card.is_out_of_stock:
            purchase_text = "⚠️ OUT OF STOCK"
            callback_data = f"outofstock_{card.card_number}"
        else:
            purchase_text = "🛒Purchase"
            callback_data = f"purchase_{card.card_number}"
        keyboard.append([
            InlineKeyboardButton(f"{i}. {card.card_number[:6]}xx", callback_data=f"card_{card.card_number}"),
            InlineKeyboardButton(purchase_text, callback_data=callback_data)
        ])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("First↩️", callback_data=f"page_1_{filter_type or ''}"))
        nav_buttons.append(InlineKeyboardButton("Back⬅️", callback_data=f"page_{page-1}_{filter_type or ''}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next➡️", callback_data=f"page_{page+1}_{filter_type or ''}"))
        nav_buttons.append(InlineKeyboardButton("Last↪️", callback_data=f"page_{total_pages}_{filter_type or ''}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([
        InlineKeyboardButton("💰 Deposit", callback_data="deposit"),
        InlineKeyboardButton("Refresh🔂", callback_data=f"refresh_{page}_{filter_type or ''}"),
        InlineKeyboardButton("🔍 Filters", callback_data="show_filters")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"edit_message_text failed: {e}")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)


async def send_stock_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_update_time():
        await update.callback_query.answer("The bot is currently updating, please wait", show_alert=True)
        return
    if not card_generator.cards:
        await card_generator.update_cards()
    cards, total_pages = card_generator.get_cards_paginated(1)
    if not cards:
        await update.callback_query.message.reply_text("No cards available at the moment.")
        return
    user = user_manager.get_or_create_user(update)
    message_text = "Vanila Exchange - Main Listings V2\n\n"
    message_text += "Your Balance:\n"
    message_text += f"💵 USD : {user.usd_balance:.6f}\n\n"
    for i, card in enumerate(cards, 1):
        message_text += f"{i}. {card.card_number} {card.currency}${card.amount:.2f} at 35%"
        if card.sticker != StickerType.NONE:
            message_text += f" {card.sticker.value}"
        message_text += "\n"
    total_balance = sum(c.amount for c in cards)
    message_text += f"\nTotal Cards: {len(cards)} | Total Cards Balance: ${total_balance:.2f}\n"
    message_text += "Legend:\n🔄 = Re-listed\n🅶 = Used on Google\n🅿 = Used on PayPal\n\n"
    message_text += "Filters: None \n"
    message_text += f"Page: 1/{total_pages} | Updated: {datetime.now().strftime('%H:%M:%S')}"
    keyboard = []
    for i, card in enumerate(cards, 1):
        if card.is_out_of_stock:
            purchase_text = "⚠️ OUT OF STOCK"
            callback_data = f"outofstock_{card.card_number}"
        else:
            purchase_text = "🛒Purchase"
            callback_data = f"purchase_{card.card_number}"
        keyboard.append([
            InlineKeyboardButton(f"{i}. {card.card_number[:6]}xx", callback_data=f"card_{card.card_number}"),
            InlineKeyboardButton(purchase_text, callback_data=callback_data)
        ])
    nav_buttons = []
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton("Next➡️", callback_data=f"page_2_"))
        nav_buttons.append(InlineKeyboardButton("Last↪️", callback_data=f"page_{total_pages}_"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([
        InlineKeyboardButton("💰 Deposit", callback_data="deposit"),
        InlineKeyboardButton("Refresh🔂", callback_data="refresh_1_"),
        InlineKeyboardButton("🔍 Filters", callback_data="show_filters")
    ])
    await update.callback_query.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))


# =========================================================
#  BALANCE / WITHDRAW / DEPOSIT
# =========================================================
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    last_update = datetime.now(timezone.utc) - timedelta(minutes=2)
    last_update_str = last_update.strftime("%Y-%m-%d %H:%M:%S UTC")
    text = (
        f"Name : {user.first_name}\n"
        f"ID : `{user.user_id}`\n"
        f"Your balance USD : `{user.usd_balance:.6f}`\n"
        f"Balance last Update : {last_update_str}"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💰Deposit", callback_data="deposit")]])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    text = (
        "💎 Account Details\n"
        f"👤 Name: {user.first_name}\n"
        f"🆔 ID: `{user.user_id}`\n"
        f"💰 Balance: `{user.usd_balance:.5f}` USD"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm", callback_data="withdraw_confirm")]])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def withdraw_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg = await query.message.reply_text("⚙️Checking  Balance.....")
    await asyncio.sleep(3)
    try:
        await msg.edit_text("⚠️ Your balance is currently empty. Deposit  to start withdrawing!")
    except Exception:
        await query.message.reply_text("⚠️ Your balance is currently empty. Deposit  to start withdrawing!")


DEPOSIT_MENU_TEXT = (
    "🏦 Vanila Exchange Deposit\n"
    "―――――――――――――――――――\n"
    "🪙 Accepted coins\n"
    "LTC  BTC  SOL  \n"
    "―――――――――――――――――――\n"
    "✅  Minimum   $15\n"
    "🕐  Expires :   30 Minutes \n"
    "⚡  Confirms  ~1–2 min\n"
    "―――――――――――――――――――\n"
    "⚠️ Send the exact amount to the correct address.\n"
    "Wrong amount or address = loss of funds.\n"
    "👇 Select amount:"
)


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            DEPOSIT_MENU_TEXT,
            reply_markup=keyboard_builder.get_deposit_amount_keyboard()
        )
    else:
        await update.message.reply_text(
            DEPOSIT_MENU_TEXT,
            reply_markup=keyboard_builder.get_deposit_amount_keyboard()
        )


async def deposit_amount_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
    query = update.callback_query
    await query.answer()
    context.user_data['deposit_amount'] = amount
    text = (
        f"🏦 DEPOSIT {amount:.0f}\n\n"
        "🪙 Choose payment coin:\n\n"
        "  🪙 LTC  — Litecoin\n"
        "  🟣  SOL  — Solana\n"
        "   ₿  BTC  — Bitcoin"
    )
    try:
        await query.edit_message_text(text, reply_markup=keyboard_builder.get_coin_keyboard())
    except Exception as e:
        logger.error(f"coin menu edit failed: {e}")
        await query.message.reply_text(text, reply_markup=keyboard_builder.get_coin_keyboard())


async def deposit_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_custom_amount'] = True
    try:
        await query.edit_message_text(
            "✏️ Custom Deposit Amount\n\n"
            "Enter amount in USD (Minimum $15)\n\n"
            "Then choose your coin — address generates instantly."
        )
    except Exception as e:
        logger.error(f"custom start edit failed: {e}")
        await query.message.reply_text(
            "✏️ Custom Deposit Amount\n\n"
            "Enter amount in USD (Minimum $15)\n\n"
            "Then choose your coin — address generates instantly."
        )


async def handle_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get('awaiting_custom_amount'):
        return False
    txt = update.message.text.strip()
    try:
        amount = float(txt)
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return True

    if amount < 15:
        await update.message.reply_text(
            "❌ Minimum deposit is $15\n\nTry again with a larger amount."
        )
        return True

    context.user_data['awaiting_custom_amount'] = False
    context.user_data['deposit_amount'] = amount

    text = (
        f"🏦 DEPOSIT {amount:.0f}\n\n"
        "🪙 Choose payment coin:\n\n"
        "  🪙 LTC  — Litecoin\n"
        "  🟣  SOL  — Solana\n"
        "   ₿  BTC  — Bitcoin"
    )
    await update.message.reply_text(text, reply_markup=keyboard_builder.get_coin_keyboard())
    return True


async def deposit_coin_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    coin = query.data.split("_")[-1]
    if coin not in COIN_META:
        await query.edit_message_text("❌ Unknown coin. Please try again with /deposit")
        return

    amount = context.user_data.get('deposit_amount')
    if not amount:
        await query.edit_message_text("⌛ Session expired. Please send /deposit again.")
        return

    meta = COIN_META[coin]
    address = random.choice(meta["addresses"])

    # লাইভ রেট
    try:
        rate = await asyncio.to_thread(fetch_crypto_rate_usd_sync, coin)
    except Exception:
        rate = float(meta["fallback"])
    if rate <= 0:
        rate = float(meta["fallback"])

    send_amount = amount / rate
    user = user_manager.get_or_create_user(update)
    order_number = user_manager.get_next_order_number()
    valid_till = datetime.now(timezone.utc) + timedelta(minutes=30)
    valid_till_str = valid_till.strftime("%Y-%m-%d %H:%M:%S UTC")

    chat_id = update.effective_chat.id

    # ---------- QR তৈরি ----------
    qr = qrcode.make(address)
    qr_bytes = BytesIO()
    qr.save(qr_bytes, format='PNG')
    qr_bytes.seek(0)

    # ---------- ১) QR ছবি (শুধু ছোট caption) ----------
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=qr_bytes,
            caption=f"📸 Scan the QR code to pay\n🏦 {coin} Address:\n`{address}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"QR send failed: {e}")

    # ---------- ২) বিস্তারিত invoice আলাদা text message ----------
    invoice_text = (
        "Here are the details:\n"
        f"Send *{coin}* to the address shown below:\n\n"
        "📸 Scan the QR code or copy the address to proceed with payment.\n\n"
        f"🏦 *{coin}* Address: `{address}`\n"
        f"💎 Currency : {coin}\n"
        f"Deposit Amount : $ {amount:.2f}\n"
        f"Rate used: 1 {coin} ≈ ${rate:.2f}\n"
        f"💸 Send Exactly: `{send_amount:.8f} {coin}`\n\n"
        f"⚠️ Only send *{coin}* assets to this address. Other assets will be lost forever.\n"
        f"Charge ID: `{user.user_id}`\n"
        f"Valid till: `{valid_till_str}`\n"
        "More details:\n"
        f"Payment ID: `{user.user_id}`\n"
        f"Order number: `{order_number}`\n\n"
        "1. Make sure you deposit the exact value to get the funds. If the value is lower than the invoice value, your funds may not be deposited.\n"
        f"Any issue, contact @{CONTACT_USERNAME} with your charge ID.\n"
        "2. Do not deposit two times to this same address. Only deposit once.\n"
        "3. Deposit to this address within 30 Minuets. After 30 Minuets this address is not valid anymore. You will need to create a new deposit by typing /deposit.\n"
        "4. If you sent money and are waiting for confirmations, do not create another invoice. Wait for the money to get confirmed.\n"
        "5. Your balance will be automatically credited to your account within 2 minutes of your deposit."
    )
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✆Contract", url=f"https://t.me/{CONTACT_USERNAME}")
    ]])

    sent_invoice = None
    try:
        sent_invoice = await context.bot.send_message(
            chat_id=chat_id,
            text=invoice_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Markdown invoice failed, trying plain text: {e}")
        try:
            sent_invoice = await context.bot.send_message(
                chat_id=chat_id,
                text=invoice_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"Plain invoice also failed: {e2}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Failed to send invoice. Try /deposit again."
            )
            return

    # কয়েন-সিলেক্ট মেসেজ ডিলিট
    try:
        await query.message.delete()
    except Exception as e:
        logger.error(f"Could not delete coin-select msg: {e}")

    context.user_data.pop('deposit_amount', None)

    # ৩১ মিনিট পর মেসেজ ডিলিট + expiry message
    job_queue = context.application.job_queue
    if job_queue and sent_invoice:
        job_queue.run_once(
            deposit_expired_job,
            when=31 * 60,
            data={
                'chat_id': chat_id,
                'message_id': sent_invoice.message_id,
                'coin': coin,
            },
            name=f"dep_expire_{user.user_id}_{sent_invoice.message_id}"
        )


async def deposit_expired_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data['chat_id'], message_id=data['message_id'])
    except Exception as e:
        logger.error(f"Failed to delete expired invoice: {e}")
    try:
        await context.bot.send_message(
            chat_id=data['chat_id'],
            text=(
                f"⚠️ Your {data['coin']} deposit session has expired! ⌛\n"
                "Please send /deposit to continue. ✨"
            )
        )
    except Exception as e:
        logger.error(f"Failed to send expiration msg: {e}")


# ---------- PROFILE / REF / HELP ----------
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    last_cards_text = '\n  '.join(['• No cards purchased yet.'] if not user.purchased_cards
                                   else [f'• {c}' for c in user.purchased_cards[-3:]])
    profile_text = (
        "Vanila Exchange PROFILE\n\n"
        f"👤 {user.first_name}\n"
        "🧠 It is impossible to love and to be wise.\n"
        "💬 By: Francis Bacon\n\n"
        f"🆔 User ID: {user.user_id}\n"
        f"🔹 Username: @{user.username}\n"
        f"💰 USD Balance: {user.usd_balance:.10f}\n\n"
        "📥 Deposits\n"
        f"• Total USD: {user.total_deposits_usd:.4f}\n"
        f"• Last: {user.last_deposit}\n\n"
        "🛒 Purchases\n"
        f"• Count: {user.purchase_count}\n"
        f"• USD Spent: ${user.usd_spent:.2f}\n"
        f"• Last Cards:\n  {last_cards_text}\n\n"
        "👥 Referrals\n"
        f"• Invited: {user.referrals_count}\n"
        f"• Referred By: {user.referral_link}\n\n"
        "🛠 Permissions\n"
        "• Vendor: ❌\n"
        "• Re-list: ❌\n\n"
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.message.reply_text(profile_text)


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_manager.get_or_create_user(update)
    if not user.referral_link or BOT_USERNAME not in user.referral_link:
        user.referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.user_id}"
    text = (
        "🎉 REFERRAL PROGRAM\n\n"
        "Invite friends and earn 5% every deposit each active referral!\n\n"
        f"🔗 Your unique link: {user.referral_link}\n\n"
        "📊 Stats\n"
        f"• Total referrals: {user.referrals_count}\n"
        "• Earned: $0.00\n\n"
        "❗ Rules\n"
        "- Bonus awarded when referral completes first transaction\n"
        "- No self-referrals\n"
        "- Fraudulent referrals will be banned"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("If you need help, please contact @Vanila_card_prepaid")


async def refund_rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = (
        "⚡️⚡️⚡️ VERY IMPORTANT ⚡️⚡️⚡️\n"
        "💳 Vanila Exchange – Refund Policy 💳\n\n"
        "✅✅✅ CARD REFUND REQUIREMENTS ✅✅✅\n"
        "1️⃣ Refund requests must be submitted within 25 minutes of purchase.\n"
        "2️⃣ Refunds are accepted ONLY if the card is stolen or partially used.\n"
        "3️⃣ You must have a valid Telegram username set.\n\n"
        "💬 Official Refund Support: https://t.me/Vanila_card_prepaid\n\n"
        "❌❌❌ AUTOMATIC REFUND REJECTIONS ❌❌❌\n"
        "🚫 No refund for ReListed cards\n"
        "🚫 No refund for cards used with Google / Google Pay\n"
        "🚫 No Telegram username = Auto rejection\n\n"
        "⚠️ IMPORTANT NOTICE: All cards are checked immediately before delivery\n"
        "📩 Need help? Contact support: https://t.me/Vanila_card_prepaid"
    )
    await update.message.reply_text(rules)


async def cents_listing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_update_time():
        await update.message.reply_text("The bot is currently updating, please wait")
        return
    if not card_generator.cards:
        await card_generator.update_cards()
    cards, total_pages = card_generator.get_low_amount_cards_page()
    await send_listing_page(update, context, cards, 1, total_pages, "Low Amount (<$0.99)")


async def scheduled_update(context: ContextTypes.DEFAULT_TYPE):
    await card_generator.update_cards()


async def auto_mark_out_of_stock(context: ContextTypes.DEFAULT_TYPE):
    if not card_generator.cards:
        return
    count = card_generator.mark_random_cards_out_of_stock(1.0)
    if count and count > 0:
        print(f"Auto OUT OF STOCK: {count} cards marked at {datetime.now()}")


# =========================================================
#  CALLBACK HANDLER
# =========================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # ---- PURCHASE ----
    if data.startswith("purchase_"):
        card_number = data.split("_", 1)[1]
        target_card = next((c for c in card_generator.cards if c.card_number == card_number), None)
        if not target_card:
            await query.answer("Card not found.", show_alert=True)
            return
        if target_card.currency == "CAD":
            total_cost_usd = target_card.amount * 0.35 * CAD_TO_USD_RATE
        else:
            total_cost_usd = target_card.amount * 0.35
        info_text = (
            "❗Vanilla cards prepaid - Listing Information\n\n"
            f"Card information: {target_card.card_number[:6]}xx\n"
            "Purchase Rate: 35%\n"
            f"Balance: {target_card.currency}${target_card.amount:.2f}\n"
            f"Total Cost: USD${total_cost_usd:.2f}\n"
            f"Registration Status: {'Registered' if target_card.is_registered else 'Unregistered'}\n"
            "Card Status: Fresh\n"
            "Click Confirm to proceed with purchase"
        )
        await query.answer()
        await query.message.reply_text(info_text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{card_number}"),
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{card_number}")
        ]]))
        return

    if data.startswith("cancel_"):
        await query.answer()
        await query.edit_message_text("❌ Purchase cancelled.")
        return

    if data.startswith("confirm_"):
        await query.answer()
        await query.edit_message_text("🔄 Your purchase is being prepared...")
        await asyncio.sleep(1)
        await query.edit_message_text("💰 Verifying your balance...")
        await asyncio.sleep(1)
        await query.edit_message_text(
            "❌ Insufficient balance. Please deposit funds and try again. OR Please contact with Admin: @Vanila_card_prepaid"
        )
        return

    if data.startswith("outofstock_"):
        await query.answer("Sorry, the card is out of stock ⚠", show_alert=True)
        return

    await query.answer()

    if await is_update_time():
        try:
            await query.edit_message_text("The bot is currently updating, please wait")
        except Exception:
            pass
        return

    # ---- MENU ----
    if data == "stock":
        await send_stock_reply(update, context)
    elif data == "profile":
        await profile_command(update, context)
    elif data == "refer":
        await ref_command(update, context)
    elif data == "deposit":
        await deposit_command(update, context)
    elif data == "withdraw":
        await withdraw_command(update, context)
    elif data == "withdraw_confirm":
        await withdraw_confirm_callback(update, context)
    # ---- DEPOSIT AMOUNT BUTTONS ----
    elif data.startswith("dep_amt_"):
        try:
            amount = float(data.replace("dep_amt_", ""))
        except ValueError:
            return
        await deposit_amount_selected(update, context, amount)
    elif data == "dep_custom":
        await deposit_custom_start(update, context)
    # ---- DEPOSIT COIN BUTTONS ----
    elif data.startswith("dep_coin_"):
        await deposit_coin_selected(update, context)
    # ---- CARD COPY ----
    elif data.startswith("card_"):
        card_num = data.replace("card_", "")
        await query.answer(f"✅ Copied: {card_num}", show_alert=False)
    # ---- PAGINATION ----
    elif data.startswith("page_"):
        parts = data.split("_")
        page = int(parts[1])
        filter_type = parts[2] if len(parts) > 2 and parts[2] else None
        cards, total_pages = card_generator.get_cards_paginated(page, filter_type=filter_type)
        await send_listing_page(update, context, cards, page, total_pages, filter_type)
    elif data.startswith("refresh_"):
        parts = data.split("_")
        page = int(parts[1])
        filter_type = parts[2] if len(parts) > 2 and parts[2] else None
        cards, total_pages = card_generator.get_cards_paginated(page, filter_type=filter_type)
        await send_listing_page(update, context, cards, page, total_pages, filter_type)
    elif data == "show_filters":
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard_builder.get_filters_keyboard())
        except Exception as e:
            logger.error(f"show_filters failed: {e}")
    elif data.startswith("filter_"):
        filter_type = data.replace("filter_", "")
        cards, total_pages = card_generator.get_cards_paginated(1, filter_type=filter_type)
        await send_listing_page(update, context, cards, 1, total_pages, filter_type)
    elif data == "clear_filters":
        cards, total_pages = card_generator.get_cards_paginated(1)
        await send_listing_page(update, context, cards, 1, total_pages)


# ---------- MESSAGE HANDLER ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_custom_amount'):
        handled = await handle_custom_amount(update, context)
        if handled:
            return

    user = user_manager.get_or_create_user(update)
    if user.user_id == ADMIN_ID and context.user_data.get('broadcast_mode', False):
        await admin_broadcast(update, context)
        return
    await update.message.reply_text("Use /help for assistance.")


# ---------- MAIN ----------
async def main():
    print("Starting bot...")
    await card_generator.update_cards()
    print(f"Bot started with {len(card_generator.cards)} cards")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("listings", stock_command))
    application.add_handler(CommandHandler("cents_listing", cents_listing))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("withdraw", withdraw_command))
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("refund_rules", refund_rules_command))
    application.add_handler(CommandHandler("ref", ref_command))
    application.add_handler(CommandHandler("admin", admin_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    if application.job_queue:
        application.job_queue.run_repeating(auto_mark_out_of_stock, interval=3600, first=3600)
        application.job_queue.run_daily(scheduled_update, time=time(hour=3, minute=0, second=0))

    print("Starting polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    while True:
        await asyncio.sleep(3600)


def start_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
