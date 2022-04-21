cd /d %~dp0
@REM cd /d %cd%

@REM echo %~dp0
@REM echo %cd%

@echo off
chcp 65001
if "%~1"=="" (
        set /p url=请输入url:
    ) else (
        set url= %1
    )

python "D:\Note\02-Computer\program\python\python-repo\94_crawler\94.py" md %url%

pause
