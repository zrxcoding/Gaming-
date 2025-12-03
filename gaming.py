"""
Gaming Utility Bot (Telegram) - Full Offline bot.py

Features:
- /start shows Start, Password, Menu (Free Fire, BGMI, COD)
- Password unlock (set env BOT_PASSWORD; default "1234")
- Game selection -> ask device model -> show submenu
- Submenu: Sensitivity + DPI, Internal Settings (step-by-step), Lag Fix, In-game Settings,
           In-game Problems Fixing, Control Layout Suggestions, Save Profile, Load Profile
- Uses internal DEVICES database for device-specific presets; fallback dynamic rules if device unknown
- Profiles saved locally in 'profiles.json' per user_id

Requirements:
- Python 3.9+
- python-telegram-bot==20.3

Setup:
1) pip install python-telegram-bot==20.3
2) export TG_BOT_TOKEN="your_token_here"
   export BOT_PASSWORD="yourpass"   # optional
3) python bot.py
"""

import os
import json
from typing import Dict, Any
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# -------------------------
# Configuration / DB
# -------------------------
PROFILES_FILE = Path("profiles.json")

# Minimal device DB (sample). You can expand this list as needed.
# Structure:
# DEVICES["device_name_lower"] = {
#    "ram_gb": int (approx), "cpu_tier": "low"/"mid"/"high",
#    "presets": { "freefire": {...}, "bgmi": {...}, "cod": {...} },
#    "internal_steps": [...],
#    "lag_fix": [...]
# }
DEVICES: Dict[str, Dict[str, Any]] = {
    "poco x3": {
        "ram_gb": 6,
        "cpu_tier": "mid",
        "presets": {
            "freefire": {
                "dpi": 480, "cm360_suggested": [25, 30, 35],
                "recommended_in_game": {"graphics": "Medium", "fps": "30-60 (try 40)"}
            },
            "bgmi": {
                "dpi": 480, "cm360_suggested": [30, 35, 40],
                "recommended_in_game": {"graphics": "Medium", "fps": "30"}
            },
            "cod": {
                "dpi": 480, "cm360_suggested": [25, 30, 35],
                "recommended_in_game": {"graphics": "Medium", "fps": "60 (if stable)"}
            }
        },
        "internal_steps": [
            "Reboot device before starting.",
            "Enable High Performance in battery settings.",
            "Disable battery saver and aggressive background restrictions for the game.",
            "Keep at least 3 GB free storage.",
            "Turn off adaptive brightness while gaming."
        ],
        "lag_fix": [
            "Close background apps and clear cache.",
            "Limit background sync and auto-updates while playing.",
            "Use Wi-Fi for stable connection; check ping.",
            "If overheating, lower graphics to Low/Medium."
        ]
    },
    "iphone 12": {
        "ram_gb": 4,
        "cpu_tier": "high",
        "presets": {
            "freefire": {"dpi": 400, "cm360_suggested": [18, 20, 22], "recommended_in_game": {"graphics": "High", "fps": "60"}},
            "bgmi": {"dpi": 400, "cm360_suggested": [20, 22, 25], "recommended_in_game": {"graphics": "High", "fps": "60"}},
            "cod": {"dpi": 400, "cm360_suggested": [18, 20, 22], "recommended_in_game": {"graphics": "High", "fps": "60"}}
        },
        "internal_steps": [
            "Close unnecessary background apps (swipe up).",
            "Keep iOS updated for best performance.",
            "Disable Low Power Mode while gaming.",
            "Free at least 10% storage for optimal performance."
        ],
        "lag_fix": [
            "Turn off background app refresh for heavy apps.",
            "Use Airplane mode + Wi-Fi to reduce mobile network interruptions.",
            "If crash persists, reinstall game."
        ]
    },
    "oneplus 9": {
        "ram_gb": 8,
        "cpu_tier": "high",
        "presets": {
            "freefire": {"dpi": 560, "cm360_suggested": [18, 22, 26], "recommended_in_game": {"graphics": "High", "fps": "60"}},
            "bgmi": {"dpi": 560, "cm360_suggested": [20, 22, 24], "recommended_in_game": {"graphics": "High", "fps": "60"}},
            "cod": {"dpi": 560, "cm360_suggested": [18, 20, 22], "recommended_in_game": {"graphics": "High", "fps": "60"}}
        },
        "internal_steps": [
            "Enable Performance Mode (Settings -> Battery -> Performance).",
            "Disable background auto-start for unneeded apps.",
            "Keep phone cool; avoid charging while gaming."
        ],
        "lag_fix": [
            "Clear game cache, reboot, and test again.",
            "Reduce render distance and shadows if thermal throttling occurs."
        ]
    }
}

SUPPORTED_GAMES = {
    "game_freefire": "freefire",
    "game_bgmi": "bgmi",
    "game_cod": "cod"
}

# -------------------------
# Utilities
# -------------------------
def load_profiles() -> Dict[str, Any]:
    if not PROFILES_FILE.exists():
        return {}
    try:
        return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_profiles(profiles: Dict[str, Any]):
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2), encoding="utf-8")

def get_device_key(name: str) -> str:
    return name.strip().lower()

def dynamic_device_profile(device_name: str) -> Dict[str, Any]:
    """
    Create a fallback device profile using simple heuristics (RAM & cpu_tier guesses).
    No external sources used.
    """
    dn = device_name.lower()
    profile = {
        "ram_gb": 4,
        "cpu_tier": "mid",
        "presets": {},
        "internal_steps": [],
        "lag_fix": []
    }
    # heuristic
    if any(k in dn for k in ["lite", "y", "entry", "c3", "a03"]):
        profile["ram_gb"] = 2
        profile["cpu_tier"] = "low"
    elif any(k in dn for k in ["pro", "plus", "max", "ultra", "9", "8", "7", "oneplus", "samsung s"]):
        profile["ram_gb"] = 8
        profile["cpu_tier"] = "high"
    else:
        profile["ram_gb"] = 4
        profile["cpu_tier"] = "mid"

    # generate basic presets for three games
    base_dpi = 400
    if profile["cpu_tier"] == "low":
        base_dpi = 360
    elif profile["cpu_tier"] == "mid":
        base_dpi = 480
    else:
        base_dpi = 560

    for g in ["freefire", "bgmi", "cod"]:
        if g == "freefire":
            cm = [25, 30, 35] if profile["cpu_tier"] != "high" else [18, 22, 26]
        elif g == "bgmi":
            cm = [30, 35, 40] if profile["cpu_tier"] != "high" else [20, 25, 30]
        else:  # cod
            cm = [25, 30, 35] if profile["cpu_tier"] != "high" else [18, 22, 26]

        profile["presets"][g] = {
            "dpi": base_dpi,
            "cm360_suggested": cm,
            "recommended_in_game": {"graphics": "Low/Medium" if profile["cpu_tier"] == "low" else "Medium" if profile["cpu_tier"] == "mid" else "High",
                                    "fps": "30" if profile["cpu_tier"] == "low" else "30-60" if profile["cpu_tier"] == "mid" else "60"}
        }

    # generic internal steps
    profile["internal_steps"] = [
        "Reboot before gaming.",
        "Close background apps.",
        "Keep at least 2-5 GB free storage.",
        "Disable battery saver and aggressive background restrictions for the game.",
        "Lower graphics if device heats up."
    ]
    profile["lag_fix"] = [
        "Close background apps and clear cache.",
        "Use stable Wi-Fi and check ping.",
        "Lower in-game graphics and FPS if needed."
    ]
    return profile

def cm360_to_sensitivity(cm360: float, dpi: int, game_scale: float = 0.022) -> float:
    """
    Basic approximation converting cm/360 and DPI to a generic in-game sensitivity.
    This is an approximation and different games have different internal scalars.
    """
    inches = cm360 * 0.393701
    raw = 360 / (inches * dpi) if inches > 0 else 0
    sens = raw * game_scale
    return round(sens, 4)

# -------------------------
# Bot Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("1. Start", callback_data="start_main")],
        [InlineKeyboardButton("2. Password", callback_data="password")],
        [InlineKeyboardButton("3. Menu (Free Fire / BGMI / COD)", callback_data="menu_games")]
    ]
    await update.message.reply_text("🔥 Gaming Utility Bot ready. Choose:", reply_markup=InlineKeyboardMarkup(kb))
    return

async def start_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "start_main":
        await query.edit_message_text("Welcome! Use Menu to start or Password to unlock advanced options.")
        return

    if data == "password":
        await query.edit_message_text("Enter password to unlock advanced features (type password):")
        # set flag so universal text handler can treat next text as password attempt
        context.user_data['awaiting_password'] = True
        return

    if data == "menu_games":
        kb = [
            [InlineKeyboardButton("Free Fire", callback_data="game_freefire")],
            [InlineKeyboardButton("BGMI", callback_data="game_bgmi")],
            [InlineKeyboardButton("COD Mobile", callback_data="game_cod")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]
        await query.edit_message_text("Choose a game:", reply_markup=InlineKeyboardMarkup(kb))
        return

async def game_select_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Cancelled. Use /start to go back.")
        return

    if data.startswith("game_"):
        game_key = SUPPORTED_GAMES.get(data, None)
        if not game_key:
            await query.edit_message_text("Game not supported.")
            return
        context.user_data['selected_game'] = game_key
        await query.edit_message_text(f"Selected game: {game_key.upper()}\nNow send your device model (e.g., 'Xiaomi Poco X3'):")
        # next text message will be treated as device
        context.user_data['awaiting_device'] = True
        return

async def build_submenu_for_device(chat_id: int, user_data: Dict[str, Any]):
    device = user_data.get('device', 'Unknown device')
    game = user_data.get('selected_game', 'unknown').upper()
    kb = [
        [InlineKeyboardButton("Sensitivity + DPI", callback_data="sub_sensitivity")],
        [InlineKeyboardButton("Internal Setting (step-by-step)", callback_data="sub_internal")],
        [InlineKeyboardButton("Lag / Heating Fix", callback_data="sub_lagfix")],
        [InlineKeyboardButton("In-game Settings", callback_data="sub_ingame")],
        [InlineKeyboardButton("In-game Problems Fixing", callback_data="sub_problems")],
        [InlineKeyboardButton("Control Layout Suggestions", callback_data="sub_controls")],
        [InlineKeyboardButton("Save Profile", callback_data="sub_save_profile"),
         InlineKeyboardButton("Load Profile", callback_data="sub_load_profile")],
        [InlineKeyboardButton("Back to Games", callback_data="back_games")]
    ]
    return InlineKeyboardMarkup(kb)

async def submenu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    device = context.user_data.get('device', 'Unknown device')
    game = context.user_data.get('selected_game', 'unknown').lower()

    if data == "back_games":
        kb = [
            [InlineKeyboardButton("Free Fire", callback_data="game_freefire")],
            [InlineKeyboardButton("BGMI", callback_data="game_bgmi")],
            [InlineKeyboardButton("COD Mobile", callback_data="game_cod")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]
        await query.edit_message_text("Choose a game:", reply_markup=InlineKeyboardMarkup(kb))
        # clear device & game in user_data if you want; keep for convenience
        context.user_data.pop('device', None)
        context.user_data.pop('selected_game', None)
        return

    # Sensitivity flow
    if data == "sub_sensitivity":
        # ask DPI
        await query.edit_message_text("Sensitivity selected.\nSend your DPI (e.g., 400 / 480 / 560):")
        context.user_data['awaiting_dpi'] = True
        return

    if data == "sub_internal":
        # provide internal steps based on device DB or dynamic profile
        dev_key = get_device_key(device)
        if dev_key in DEVICES:
            steps = DEVICES[dev_key]['internal_steps']
        else:
            profile = dynamic_device_profile(device)
            steps = profile['internal_steps']
        text = f"Internal settings guide for {device}:\n\n" + "\n".join(steps)
        await query.edit_message_text(text, reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    if data == "sub_lagfix":
        dev_key = get_device_key(device)
        if dev_key in DEVICES:
            steps = DEVICES[dev_key]['lag_fix']
        else:
            profile = dynamic_device_profile(device)
            steps = profile['lag_fix']
        text = f"Lag/Heating Fix Checklist for {device}:\n\n" + "\n".join(steps)
        await query.edit_message_text(text, reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    if data == "sub_ingame":
        dev_key = get_device_key(device)
        if dev_key in DEVICES:
            presets = DEVICES[dev_key]['presets'].get(game, {})
        else:
            profile = dynamic_device_profile(device)
            presets = profile['presets'].get(game, {})
        # pretty print
        if presets:
            text = f"In-game recommended settings for {device} ({game.upper()}):\n\n"
            rec = presets.get('recommended_in_game', {})
            for k, v in rec.items():
                text += f"- {k.capitalize()}: {v}\n"
            text += f"\nSuggested DPI: {presets.get('dpi')}\nSuggested cm/360 examples: {presets.get('cm360_suggested')}\n"
        else:
            text = f"No specific presets found for {device} / {game.upper()}. Using dynamic suggestions:\n"
            profile = dynamic_device_profile(device)
            p = profile['presets'].get(game, {})
            text += f"- DPI: {p.get('dpi')}\n- Suggested cm/360: {p.get('cm360_suggested')}\n- Recommended Graphcis/FPS: {p.get('recommended_in_game')}\n"
        await query.edit_message_text(text, reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    if data == "sub_problems":
        await query.edit_message_text("Describe the in-game problem (e.g., 'lag after 10 minutes', 'crash on launch'):")
        context.user_data['awaiting_problem'] = True
        return

    if data == "sub_controls":
        # control layout suggestion
        layout = control_layout_suggestions(game, device)
        await query.edit_message_text(layout, reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    if data == "sub_save_profile":
        # save selected device + game to profiles file for user
        uid = str(update.effective_user.id)
        profiles = load_profiles()
        entry = {
            "device": context.user_data.get('device'),
            "game": context.user_data.get('selected_game')
        }
        profiles[uid] = entry
        save_profiles(profiles)
        await query.edit_message_text(f"Profile saved for your account: {entry}", reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    if data == "sub_load_profile":
        uid = str(update.effective_user.id)
        profiles = load_profiles()
        if uid in profiles:
            entry = profiles[uid]
            context.user_data['device'] = entry.get('device')
            context.user_data['selected_game'] = entry.get('game')
            await query.edit_message_text(f"Loaded profile: {entry}", reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        else:
            await query.edit_message_text("No saved profile found. Use 'Save Profile' first.", reply_markup=await build_submenu_for_device(update.effective_chat.id, context.user_data))
        return

    # unknown
    await query.edit_message_text("Unknown submenu option. Use /start to begin.")

async def universal_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    uid = str(update.effective_user.id)

    # Password attempt
    if context.user_data.get('awaiting_password'):
        context.user_data['awaiting_password'] = False
        password = os.environ.get("BOT_PASSWORD", "1234")
        if txt == password:
            context.user_data['unlocked'] = True
            await update.message.reply_text("✅ Password correct. Advanced features unlocked!")
        else:
            await update.message.reply_text("❌ Wrong password. Try /start again.")
        return

    # Device input right after selecting game
    if context.user_data.get('awaiting_device'):
        context.user_data['awaiting_device'] = False
        device_name = txt
        context.user_data['device'] = device_name
        # Build submenu
        markup = await build_submenu_for_device(update.effective_chat.id, context.user_data)
        await update.message.reply_text(f"Got device: {device_name}\nNow choose an option:", reply_markup=markup)
        return

    # DPI awaiting
    if context.user_data.get('awaiting_dpi'):
        if not txt.isdigit():
            await update.message.reply_text("DPI should be a number like 400, 480, 560. Send DPI again:")
            return
        dpi = int(txt)
        context.user_data['dpi'] = dpi
        context.user_data['awaiting_dpi'] = False
        context.user_data['awaiting_cm360'] = True
        await update.message.reply_text("Got DPI. Now send desired cm/360 (e.g., 30) or send 'default' for suggestions:")
        return

    # cm360 awaiting
    if context.user_data.get('awaiting_cm360'):
        txt_low = txt.lower()
        dpi = context.user_data.get('dpi', 480)
        device = context.user_data.get('device', 'Unknown device')
        game = context.user_data.get('selected_game', 'unknown').upper()
        context.user_data['awaiting_cm360'] = False

        if txt_low == "default":
            dev_key = get_device_key(device)
            if dev_key in DEVICES:
                suggestions = DEVICES[dev_key]['presets'].get(game.lower(), {}).get('cm360_suggested', [])
            else:
                suggestions = dynamic_device_profile(device)['presets'].get(game.lower(), {}).get('cm360_suggested', [])
            reply = f"Suggested cm/360 for {device} ({game}): {suggestions}\n\nExamples with DPI={dpi}:\n"
            for c in suggestions:
                s = cm360_to_sensitivity(c, dpi)
                reply += f"- {c} cm/360 -> sensitivity ≈ {s}\n"
            await update.message.reply_text(reply)
            return
        else:
            try:
                cm360 = float(txt)
                sens = cm360_to_sensitivity(cm360, dpi)
                reply = (
                    f"Device: {device}\nGame: {game}\nDPI: {dpi}\ncm/360: {cm360}\n\n"
                    f"Approx. suggested in-game sensitivity: {sens}\n\n"
                    "Note: This is an approximation. Fine-tune in small increments (0.01 - 0.1) in-game."
                )
                await update.message.reply_text(reply)
                return
            except Exception:
                await update.message.reply_text("Couldn't parse cm/360. Send a number like 30 or 'default'.")
                context.user_data['awaiting_cm360'] = True
                return

    # Problem description handling
    if context.user_data.get('awaiting_problem'):
        context.user_data['awaiting_problem'] = False
        desc = txt.lower()
        device = context.user_data.get('device', 'Unknown device')
        # Very simple heuristic-based troubleshooting
        if any(k in desc for k in ["lag", "fps", "frame", "stutter"]):
            reply = (
                f"Troubleshooting (lag/fps) for {device}:\n"
                "1) Close background apps & clear cache.\n"
                "2) Lower graphics, disable shadows and AA.\n"
                "3) Use Wi-Fi or stable network; check ping.\n"
                "4) Reboot and test; if overheating reduce session time.\n"
            )
        elif any(k in desc for k in ["crash", "closing", "force close", "stopped"]):
            reply = (
                f"Troubleshooting (crash) for {device}:\n"
                "1) Update the game & OS.\n"
                "2) Clear game cache; reinstall if needed.\n"
                "3) Ensure sufficient free storage and memory.\n"
            )
        elif any(k in desc for k in ["login", "auth", "account", "ban"]):
            reply = (
                f"Troubleshooting (login/account) for {device}:\n"
                "1) Check network & server status.\n"
                "2) Try reinstall or clear cache.\n"
                "3) If linked to social login, check those credentials."
            )
        else:
            reply = (
                "Generic troubleshooting:\n"
                "- Update game & OS, clear cache.\n- Free up storage (>=2-5GB).\n- Lower graphics and test.\nIf you give a specific short description (e.g., 'fps drops after 10 min'), I'll provide targeted steps."
            )
        await update.message.reply_text(reply)
        return

    # profile-related quick commands
    if txt.lower().startswith("load profile"):
        profiles = load_profiles()
        if uid in profiles:
            p = profiles[uid]
            context.user_data['device'] = p.get('device')
            context.user_data['selected_game'] = p.get('game')
            await update.message.reply_text(f"Loaded profile: {p}")
        else:
            await update.message.reply_text("No saved profile found. Use Save Profile in submenu.")
        return

    if txt.lower().startswith("help"):
        await update.message.reply_text("Use /start to open the menu. Flow: /start -> Menu -> choose game -> send device -> choose option.")
        return

    # If user types a game name directly
    lowered = txt.lower()
    if any(k in lowered for k in ["free fire", "freefire", "ff", "bgmi", "pubg", "cod", "call of duty"]):
        # normalize
        if "free" in lowered or "freefire" in lowered or "ff" in lowered:
            context.user_data['selected_game'] = "freefire"
        elif "bgmi" in lowered or "pubg" in lowered:
            context.user_data['selected_game'] = "bgmi"
        elif "cod" in lowered or "call of duty" in lowered:
            context.user_data['selected_game'] = "cod"
        await update.message.reply_text(f"Selected {context.user_data['selected_game'].upper()}. Now send your device model (e.g., 'Poco X3'):")
        context.user_data['awaiting_device'] = True
        return

    # fallback
    await update.message.reply_text("Samjha nahi. Use /start to open menu or type 'help'.")

# -------------------------
# Control layout helper
# -------------------------
def control_layout_suggestions(game: str, device: str) -> str:
    g = game.lower()
    base = ""
    if "freefire" in g or "free fire" in g or "ff" in g:
        base = (
            "Free Fire — Suggested control layout:\n"
            "- Move: Left thumb bottom-left\n"
            "- Aim: Right thumb near center-right\n"
            "- Fire (ADS): Top-right (near right thumb)\n"
            "- Jump/Crouch/Prone: Lower-right cluster\n"
            "- Tip: Use slightly transparent fire button so crosshair remains visible."
        )
    elif "bgmi" in g or "pubg" in g:
        base = (
            "BGMI/PUBG — Suggested control layout:\n"
            "- Move: Left bottom\n"
            "- Aim: Right center\n"
            "- Fire: Right edge (use two-fire buttons for flexibility)\n"
            "- Crouch/Prone/Jump: Lower-right cluster\n"
            "- Tip: Enable gyroscope for fine aim if comfortable."
        )
    elif "cod" in g or "call of duty" in g:
        base = (
            "COD Mobile — Suggested control layout:\n"
            "- Move: Left bottom\n"
            "- Aim: Right center\n"
            "- Fire: Right edge (primary)\n"
            "- Secondary fire/ADS: small button near right thumb\n"
            "- Tip: Use tap-to-ADS or hold-to-ADS based on personal preference."
        )
    else:
        base = "Default FPS layout: Move left, aim + fire on right. Customize by feel."
    # device hint
    if "iphone" in device.lower():
        base += "\n\nDevice hint: on iPhone, buttons can be slightly smaller due to high touch accuracy."
    else:
        base += "\n\nDevice hint: On large screens, keep primary fire slightly inward for comfortable reach."
    return base

# -------------------------
# Startup
# -------------------------
def main():
    token = os.environ.get("8582595837:AAFm0YVXPYPFVWiuS6AP1ax2Ud7VeG8OX2U")
    if not token:
        print("Error: set TG_BOT_TOKEN environment variable and rerun.")
        return

    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(start_menu_router, pattern="^(start_main|password|menu_games)$"))
    app.add_handler(CallbackQueryHandler(game_select_router, pattern="^game_"))
    app.add_handler(CallbackQueryHandler(submenu_router, pattern="^(sub_|back_games|cancel|sub_save_profile|sub_load_profile)$"))

    # Universal text handler for device / dpi / problems / password
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, universal_text_router))

    print("Bot started (polling). Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()