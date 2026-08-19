@echo off
chcp 65001 > nul
:loop
python bot.py
echo Бот завершился. Перезапуск через 5 секунд...
timeout /t 5 /nobreak > nul
goto loop
