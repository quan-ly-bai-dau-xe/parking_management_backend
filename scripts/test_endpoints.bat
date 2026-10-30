@echo off
setlocal EnableDelayedExpansion
title TESTING API ENDPOINTS - SMART MOBILITY BACKEND

REM Chuyen thu muc lam viec ve project root
cd /d "%~dp0.."

REM Xac dinh duong dan pytest
set "PYTEST_CMD=.venv\Scripts\pytest.exe"
if not exist "%PYTEST_CMD%" (
    set "PYTEST_CMD=pytest"
)

REM Dinh nghia list cac file test endpoint (danh sach cach nhau boi dau cach)
set "ENDPOINTS=tests\test_health.py tests\accounts\test_core_auth.py tests\parking\test_check_in_api.py tests\parking\test_check_out_api.py tests\parking\test_vehicle_lookup_api.py tests\parking\test_vehicle_search_api.py tests\parking\test_plate_scans_api.py tests\parking\test_gates_and_sessions_api.py"

REM Neu co truyen tham so dong lenh (vi du: test_endpoints.bat 1 hoac test_endpoints.bat all)
if not "%~1"=="" (
    set "choice=%~1"
    goto PROCESS_CHOICE
)

:MENU
cls
echo ===============================================================================
echo                     DANH SACH TEST CAC API ENDPOINTS
echo ===============================================================================
echo  [1] Health Check / OpenAPI Schema    : tests\test_health.py
echo  [2] Authentication (Login/CSRF/Me)   : tests\accounts\test_core_auth.py
echo  [3] Parking Check-In Session         : tests\parking\test_check_in_api.py
echo  [4] Parking Check-Out va Tinh phi    : tests\parking\test_check_out_api.py
echo  [5] Vehicle Lookup (Bien so chuan)   : tests\parking\test_vehicle_lookup_api.py
echo  [6] Vehicle Search (Da tieu chi)     : tests\parking\test_vehicle_search_api.py
echo  [7] Plate Scan OCR                   : tests\parking\test_plate_scans_api.py
echo  [8] Gates va Sessions History        : tests\parking\test_gates_and_sessions_api.py
echo -------------------------------------------------------------------------------
echo  [A] CHAY TOAN BO DANH SACH (Loop qua list bang vong lap FOR)
echo  [C] CHAY FULL TEST SUITE VOI COVERAGE (DoD Check)
echo  [0] Thoat
echo ===============================================================================
echo.

set /p choice="Nhap lua chon cua ban (0-8, A, C): "

:PROCESS_CHOICE
if /i "%choice%"=="1" goto TEST_HEALTH
if /i "%choice%"=="2" goto TEST_AUTH
if /i "%choice%"=="3" goto TEST_CHECKIN
if /i "%choice%"=="4" goto TEST_CHECKOUT
if /i "%choice%"=="5" goto TEST_LOOKUP
if /i "%choice%"=="6" goto TEST_SEARCH
if /i "%choice%"=="7" goto TEST_PLATE
if /i "%choice%"=="8" goto TEST_GATES
if /i "%choice%"=="A" goto TEST_ALL_LIST
if /i "%choice%"=="all" goto TEST_ALL_LIST
if /i "%choice%"=="C" goto TEST_FULL_COVERAGE
if /i "%choice%"=="0" goto EXIT
if /i "%choice%"=="exit" goto EXIT

echo.
echo [LOI] Lua chon khong hop le: %choice%
if not "%~1"=="" goto EXIT
pause
goto MENU

:TEST_HEALTH
echo.
echo [RUNNING] Test Health Check / OpenAPI docs...
"%PYTEST_CMD%" tests\test_health.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_AUTH
echo.
echo [RUNNING] Test Authentication (Login, Logout, CSRF, Me)...
"%PYTEST_CMD%" tests\accounts\test_core_auth.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_CHECKIN
echo.
echo [RUNNING] Test Check-in xe vao bai...
"%PYTEST_CMD%" tests\parking\test_check_in_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_CHECKOUT
echo.
echo [RUNNING] Test Check-out va Tinh phi do xe...
"%PYTEST_CMD%" tests\parking\test_check_out_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_LOOKUP
echo.
echo [RUNNING] Test Tra cuu phuong tien theo bien so...
"%PYTEST_CMD%" tests\parking\test_vehicle_lookup_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_SEARCH
echo.
echo [RUNNING] Test Tim kiem phuong tien da tieu chi...
"%PYTEST_CMD%" tests\parking\test_vehicle_search_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_PLATE
echo.
echo [RUNNING] Test Nhan dien bien so OCR...
"%PYTEST_CMD%" tests\parking\test_plate_scans_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_GATES
echo.
echo [RUNNING] Test Cong barrier va lich su phien...
"%PYTEST_CMD%" tests\parking\test_gates_and_sessions_api.py -v --no-cov
goto PAUSE_AND_BACK

:TEST_ALL_LIST
echo.
echo ===============================================================================
echo BAT DAU CHAY TUAN TU TOAN BO DANH SACH ENDPOINTS
echo ===============================================================================
for %%F in (%ENDPOINTS%) do (
    echo.
    echo ---------------------------------------------------------------------------
    echo [*] Dang chay test: %%F
    echo ---------------------------------------------------------------------------
    "%PYTEST_CMD%" %%F -v --no-cov
    if errorlevel 1 (
        echo [CANH BAO] File test %%F bi FAIL hoac gap loi!
    )
)
echo.
echo ===============================================================================
echo HOAN THANH DUYET DANH SACH!
echo ===============================================================================
goto PAUSE_AND_BACK

:TEST_FULL_COVERAGE
echo.
echo [RUNNING] Chay toan bo test suite kem do Coverage...
"%PYTEST_CMD%"
goto PAUSE_AND_BACK

:PAUSE_AND_BACK
echo.
if not "%~1"=="" goto EXIT
pause
goto MENU

:EXIT
echo Tam biet!
endlocal
exit /b 0
