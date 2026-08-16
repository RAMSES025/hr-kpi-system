import webview
import threading
import uvicorn
import time

# Импортируем наше приложение FastAPI из файла main.py
from main import app

def run_server():
    # Запускаем Uvicorn в фоновом режиме. 
    # log_level="warning" отключит спам в терминале, оставляя только важные ошибки.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

if __name__ == '__main__':
    # 1. Запускаем сервер FastAPI в отдельном параллельном потоке.
    # Если запустить его в основном потоке, код "зависнет" на сервере, и окно никогда не откроется.
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # 2. Даем серверу буквально 1 секунду на "разогрев".
    # Если окно откроется быстрее, чем запустится сервер, вы увидите ошибку "Страница не найдена".
    time.sleep(1)

    # 3. Создаем нативное окно приложения macOS
    window = webview.create_window(
        title='Удалёнка - HR Портал', 
        url='http://127.0.0.1:8000/admin', # Сразу направляем на админ-панель
        width=1100, 
        height=800,
        min_size=(800, 600) # Ограничиваем минимальный размер, чтобы верстка Bootstrap не ломалась
    )
    
    # 4. Запускаем графический интерфейс
    webview.start()
