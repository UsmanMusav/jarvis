@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0.."

rem ============================================================
rem  Привязка проекта к вашему репозиторию на GitHub (Windows)
rem  Запуск:   tools\setup_github.bat ваш-логин/jarvis
rem ============================================================

set "REPO=%~1"
if "%REPO%"=="" (
    echo Укажите репозиторий в формате логин/название, например:
    echo     tools\setup_github.bat ivanov/jarvis
    pause & exit /b 1
)
echo %REPO% | find "/" >nul || (
    echo Нужен формат логин/название, через косую черту.
    pause & exit /b 1
)

where git >nul 2>nul || (echo [!] Git не установлен: https://git-scm.com/download/win & pause & exit /b 1)
where python >nul 2>nul || (echo [!] Python не найден в PATH & pause & exit /b 1)

for /f "delims=" %%v in ('python -c "import sys;sys.path.insert(0,'.');from core.version import __version__;print(__version__)"') do set VER=%%v
set "URL=https://github.com/%REPO%"

echo ============================================================
echo   Репозиторий : %URL%
echo   Версия      : %VER%
echo ============================================================
echo.
echo Перед продолжением создайте ПУСТОЙ репозиторий:
echo     https://github.com/new    (без README и .gitignore)
echo.
set /p OK="Репозиторий создан? Продолжаем? [y/N] "
if /i not "%OK%"=="y" if /i not "%OK%"=="д" (echo Отменено. & pause & exit /b 0)

echo.
echo [1/4] Подставляю адрес в файлы проекта...
python tools\_patch_repo.py "%REPO%" || goto :fail

echo.
echo [2/4] Проверяю, что всё работает...
python tests\test_commands.py  >nul && echo       команды      OK
python tests\test_assistant.py >nul && echo       диалог       OK
python tests\test_updater.py   >nul && echo       обновление   OK

echo.
echo [3/4] Git...
if not exist ".git" (git init -q & echo       репозиторий создан)
git add -A
git diff --cached --quiet || git commit -q -m "J.A.R.V.I.S. %VER% - голосовой помощник с установщиком и автообновлением"
git branch -M main
git remote remove origin 2>nul
git remote add origin "%URL%.git"
git push -u origin main || goto :fail

echo.
echo [4/4] Релиз
set /p TAG="Поставить тег v%VER% и запустить сборку установщиков? [y/N] "
if /i "%TAG%"=="y" goto :dotag
if /i "%TAG%"=="д" goto :dotag
echo Пропущено. Когда захотите выпустить релиз:
echo     git tag v%VER% ^&^& git push origin v%VER%
goto :done

:dotag
git tag v%VER% -f
git push origin v%VER% -f
echo.
echo Сборка пошла. Следить тут:  %URL%/actions
echo Установщики появятся тут:   %URL%/releases/latest

:done
echo.
echo ============================================================
echo   Готово.  %URL%
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [!] Что-то пошло не так. Смотрите сообщение выше.
pause
exit /b 1
