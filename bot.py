from flask import Flask, request
import requests
app = Flask(__name__)
TOKEN = "8757780924:AAFs370CL1zMzY-fNCpqZ65-w0vymD0DH_E"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.get_json()
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            if text == '/start':
                reply = "Бот работает! Напиши /test"
            elif text == '/test':
                reply = "Бот активен!"
            else:
                reply = "Напиши /start или /test"
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={'chat_id': chat_id, 'text': reply})
        return "ok"
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
