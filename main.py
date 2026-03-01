import telebot
from telebot import types
import requests
import os
import time
import csv
import threading
from flask import Flask # Render 7/24 için eklendi

# --- FLASK SERVER (Render Uyumasın Diye) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Calisiyor", 200

def run_flask():
    # Render portu otomatik verir, vermezse 8080 kullanır
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- AYARLAR ---
TOKENS = ["78225:AAGDicJRSSIyvlJlGbeh76GxCmx72YkA"]
API_BASE = "https://arastir.sbs/api"
ADMIN_ID = 7933303712
KANALLAR = ["@MeclisLogin"]
USER_FILE = "sorgubaslatanlar.txt"

# Hafıza Yönetimi
user_data_master = {}
sorgu_aktif_master = {}

# --- YARDIMCI FONKSİYONLAR ---
def kullanici_kaydet(user_id):
    if not os.path.exists(USER_FILE):
        with open(USER_FILE, "w") as f: pass
    
    with open(USER_FILE, "r") as f:
        ekli = f.read().splitlines()
    
    if str(user_id) not in ekli:
        with open(USER_FILE, "a") as f: 
            f.write(f"{user_id}\n")

def kanal_kontrol(bot, user_id):
    for kanal in KANALLAR:
        try:
            status = bot.get_chat_member(kanal, user_id).status
            if status in ['left', 'kicked']: return False
        except: return False
    return True

def katilma_mesaji():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="📢 Kanala Katıl", url="https://t.me/SanalPislik"))
    kb.add(types.InlineKeyboardButton(text="✅ Katıldım, Kontrol Et", callback_data="kontrol_et"))
    return "⚠️ <b>Devam edebilmek için kanalımıza katılmalısınız!</b>", kb

def ana_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(text="🔍 TC Sorgula", callback_data="sorgu_tc"),
        types.InlineKeyboardButton(text="👤 Ad Soyad", callback_data="sorgu_adsoyad"),
        types.InlineKeyboardButton(text="📱 TC'den GSM", callback_data="sorgu_tcgsm"),
        types.InlineKeyboardButton(text="📞 GSM'den TC", callback_data="sorgu_gsmtc"),
        types.InlineKeyboardButton(text="🏢 İşyeri Bilgisi", callback_data="sorgu_isyeri"),
        types.InlineKeyboardButton(text="🏠 Adres Bilgisi", callback_data="sorgu_adres"),
        types.InlineKeyboardButton(text="👨‍👩‍👧‍👦 Sülale Ağacı", callback_data="sorgu_sulale"),
        types.InlineKeyboardButton(text="🔥 Şantaj (CSV)", callback_data="sorgu_santal"),
        types.InlineKeyboardButton(text="❓ Yardım", callback_data="yardim")
    )
    return kb

def geri_buton():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🔙 Vazgeç / Ana Menü", callback_data="ana_menu"))
    return kb

def api_get(endpoint, params):
    try:
        clean_params = {k: v for k, v in params.items() if v and str(v).lower() not in ["geç", "bilmiyorum", "none"]}
        r = requests.get(f"{API_BASE}/{endpoint}", params=clean_params, timeout=25)
        return r.json() if r.status_code == 200 else None
    except: return None

# --- BOT OLUŞTURMA ---

def create_bot(token):
    bot = telebot.TeleBot(token)
    bot_id = token.split(':')[0]
    user_data_master[bot_id] = {}
    sorgu_aktif_master[bot_id] = {}

    def get_sorgu_aktif(chat_id):
        return sorgu_aktif_master[bot_id].get(chat_id, False)

    def set_sorgu_aktif(chat_id, val):
        sorgu_aktif_master[bot_id][chat_id] = val

    # --- AD SOYAD ADIMLARI ---
    
    def adsoyad_ad_al(message):
        if not message.text: return
        user_data_master[bot_id].setdefault(message.chat.id, {})['adi'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "🔡 <b>Soyadını girin:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, adsoyad_soyad_al)

    def adsoyad_soyad_al(message):
        if not message.text: return
        user_data_master[bot_id][message.chat.id]['soyadi'] = message.text.strip()
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⏭️ Bilmiyorum / Geç", callback_data="bilmiyorum_il"))
        msg = bot.send_message(message.chat.id, "📍 <b>İl girin:</b>", parse_mode="HTML", reply_markup=kb)
        bot.register_next_step_handler(msg, adsoyad_il_al)

    def adsoyad_il_al(message):
        chat_id = message.chat.id
        if message.text:
            text = message.text.strip()
            user_data_master[bot_id][chat_id]['il'] = "" if text.lower() == "geç" else text
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("⏭️ Bilmiyorum / Geç", callback_data="bilmiyorum_ilce"))
            msg = bot.send_message(chat_id, "🏘️ <b>İlçe girin:</b>", parse_mode="HTML", reply_markup=kb)
            bot.register_next_step_handler(msg, adsoyad_ilce_al)

    def adsoyad_ilce_al(message):
        chat_id = message.chat.id
        if message.text:
            text = message.text.strip()
            user_data_master[bot_id][chat_id]['ilce'] = "" if text.lower() == "geç" else text
            adsoyad_sorgula_final(chat_id)

    def adsoyad_sorgula_final(chat_id):
        try:
            bot.send_message(chat_id, "🔍 <b>Aranıyor...</b>", parse_mode="HTML")
            d = user_data_master[bot_id][chat_id]
            sonuc = api_get("adsoyad.php", {"adi": d.get('adi'), "soyadi": d.get('soyadi'), "il": d.get('il'), "ilce": d.get('ilce')})
            
            if sonuc:
                kayitlar = sonuc.get("data", []) if isinstance(sonuc, dict) else sonuc
                if not kayitlar:
                    bot.send_message(chat_id, "❌ Kayıt yok.", reply_markup=ana_menu())
                else:
                    dosya_adi = f"adsoyad_{chat_id}.txt"
                    with open(dosya_adi, "w", encoding="utf-8") as f:
                        for k in kayitlar:
                            f.write("👤 Kişi Bilgisi:\n")
                            if isinstance(k, dict):
                                for key, val in k.items(): f.write(f"{key}: {val}\n")
                            else: f.write(str(k) + "\n")
                            f.write("-" * 20 + "\n")
                    with open(dosya_adi, "rb") as doc:
                        bot.send_document(chat_id, doc, caption=f"✅ {len(kayitlar)} kayıt bulundu.", reply_markup=ana_menu())
                    if os.path.exists(dosya_adi): os.remove(dosya_adi)
            else:
                bot.send_message(chat_id, "❌ Kayıt yok.", reply_markup=ana_menu())
        except Exception as e:
            bot.send_message(chat_id, f"❌ Hata: {e}")
        finally:
            set_sorgu_aktif(chat_id, False)

    # --- DUYURU SİSTEMİ (ADMIN) ---

    @bot.message_handler(commands=['duyuru'])
    def cmd_duyuru(message):
        if message.from_user.id != ADMIN_ID: return
        msg = bot.reply_to(message, "📢 Tüm kullanıcılara gönderilecek mesajı yazın:")
        bot.register_next_step_handler(msg, duyuru_gonder)

    def duyuru_gonder(message):
        if not os.path.exists(USER_FILE): return
        with open(USER_FILE, "r") as f:
            user_list = f.read().splitlines()
        
        basarili = 0
        hatali = 0
        aktif_kullanicilar = []

        status_msg = bot.send_message(ADMIN_ID, f"⏳ {len(user_list)} kişiye duyuru başlatıldı...")

        for uid in user_list:
            try:
                bot.send_message(uid, message.text)
                aktif_kullanicilar.append(uid)
                basarili += 1
                time.sleep(0.05) 
            except:
                hatali += 1
                continue
        
        with open(USER_FILE, "w") as f:
            for u in aktif_kullanicilar: f.write(f"{u}\n")
        
        with open(USER_FILE, "rb") as doc:
            bot.send_document(ADMIN_ID, doc, caption=f"✅ Duyuru Tamamlandı\n\n🟢 Başarılı: {basarili}\n🔴 Silinen: {hatali}\n📊 Toplam Aktif: {len(aktif_kullanicilar)}")

    # --- DİĞER İŞLEMLER ---

    def santal_islem(message):
        try:
            chat_id = message.chat.id
            hedef_tc = message.text.strip()
            if not (hedef_tc.isdigit() and len(hedef_tc) == 11):
                bot.send_message(chat_id, "❌ Hatalı TC!", reply_markup=ana_menu())
                return
            
            bot.send_message(chat_id, "⏳ Veriler işleniyor, lütfen bekleyin...")
            sulale_data = api_get("sulale.php", {"tc": hedef_tc})
            if not sulale_data:
                bot.send_message(chat_id, "❌ Veri bulunamadı.", reply_markup=ana_menu())
                return

            kayitlar = sulale_data if isinstance(sulale_data, list) else [sulale_data]
            csv_dosya = f"santal_{chat_id}.csv"
            found = 0
            
            with open(csv_dosya, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["Name", "Phone 1 - Value"])
                for k in kayitlar:
                    if isinstance(k, dict) and "TC" in k:
                        gsm = api_get("tcgsm.php", {"tc": k.get("TC")})
                        if gsm:
                            num_data = gsm[0] if isinstance(gsm, list) else gsm
                            num = num_data.get("GSM") if isinstance(num_data, dict) else None
                            if num:
                                found += 1
                                writer.writerow([f"Kayıt_{found}", num])
            
            if found > 0:
                with open(csv_dosya, "rb") as f:
                    bot.send_document(chat_id, f, caption=f"✅ {found} adet numara dışa aktarıldı.", reply_markup=ana_menu())
            else: 
                bot.send_message(chat_id, "❌ Numara bulunamadı.", reply_markup=ana_menu())
            
            if os.path.exists(csv_dosya): os.remove(csv_dosya)
        except: pass
        finally: set_sorgu_aktif(message.chat.id, False)

    def tc_sorgu_isle(message):
        try:
            chat_id = message.chat.id
            tc = message.text.strip()
            bot.send_message(chat_id, "🔍 Sorgulanıyor...")
            stipi = user_data_master[bot_id].get(chat_id, {}).get('sorgu_tipi', 'tc')
            sonuc = api_get(f"{stipi}.php", {"tc": tc})
            
            if sonuc:
                dosya = f"res_{chat_id}.txt"
                with open(dosya, "w", encoding="utf-8") as f:
                    f.write(str(sonuc))
                with open(dosya, "rb") as d: 
                    bot.send_document(chat_id, d, reply_markup=ana_menu())
                if os.path.exists(dosya): os.remove(dosya)
            else: 
                bot.send_message(chat_id, "❌ Sonuç yok.", reply_markup=ana_menu())
        except: pass
        finally: set_sorgu_aktif(chat_id, False)

    def gsmtc_sorgu_isle(message):
        try:
            chat_id = message.chat.id
            sonuc = api_get("gsmtc.php", {"gsm": message.text.strip()})
            if sonuc:
                bot.send_message(chat_id, f"✅ Sonuç:\n<code>{sonuc}</code>", parse_mode="HTML", reply_markup=ana_menu())
            else: 
                bot.send_message(chat_id, "❌ Bulunamadı.", reply_markup=ana_menu())
        except: pass
        finally: set_sorgu_aktif(chat_id, False)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_handler(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id)

        if call.data == "ana_menu":
            set_sorgu_aktif(chat_id, False)
            bot.edit_message_text("🏠 İşlem Seçin:", chat_id, call.message.message_id, reply_markup=ana_menu())
        
        elif call.data == "kontrol_et":
            if kanal_kontrol(bot, call.from_user.id):
                bot.edit_message_text("✅ Hoş geldiniz! Bir işlem seçin:", chat_id, call.message.message_id, reply_markup=ana_menu())
            else: bot.answer_callback_query(call.id, "❌ Hala kanala katılmamışsınız!", show_alert=True)

        elif not kanal_kontrol(bot, call.from_user.id):
            t, k = katilma_mesaji()
            bot.edit_message_text(t, chat_id, call.message.message_id, reply_markup=k, parse_mode="HTML")

        elif call.data == "sorgu_adsoyad":
            set_sorgu_aktif(chat_id, True)
            bot.edit_message_text("👤 Kişinin ADINI girin:", chat_id, call.message.message_id, reply_markup=geri_buton())
            bot.register_next_step_handler(call.message, adsoyad_ad_al)
        
        elif call.data == "sorgu_santal":
            set_sorgu_aktif(chat_id, True)
            bot.edit_message_text("🔥 Hedef TC girin:", chat_id, call.message.message_id, reply_markup=geri_buton())
            bot.register_next_step_handler(call.message, santal_islem)

        elif call.data == "sorgu_gsmtc":
            set_sorgu_aktif(chat_id, True)
            bot.edit_message_text("📞 Numara girin (Örn: 532...):", chat_id, call.message.message_id, reply_markup=geri_buton())
            bot.register_next_step_handler(call.message, gsmtc_sorgu_isle)

        elif call.data.startswith("sorgu_"):
            set_sorgu_aktif(chat_id, True)
            user_data_master[bot_id][chat_id] = {'sorgu_tipi': call.data.replace("sorgu_", "")}
            bot.edit_message_text("🆔 TC girin:", chat_id, call.message.message_id, reply_markup=geri_buton())
            bot.register_next_step_handler(call.message, tc_sorgu_isle)

    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        kullanici_kaydet(message.from_user.id)
        if not kanal_kontrol(bot, message.from_user.id):
            t, k = katilma_mesaji()
            bot.send_message(message.chat.id, t, reply_markup=k, parse_mode="HTML")
            return
        bot.send_message(message.chat.id, "🏠 Merhaba! Sorgu botuna hoş geldiniz. Lütfen bir işlem seçin:", reply_markup=ana_menu())

    return bot

def run_bot(token):
    bot = create_bot(token)
    while True:
        try:
            print(f"Bot Aktif: {token[:15]}...")
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Flask'ı başlat (Render uyumasın diye)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Botları başlat
    for t in TOKENS:
        threading.Thread(target=run_bot, args=(t,), daemon=True).start()
    
    while True:
        time.sleep(1)
