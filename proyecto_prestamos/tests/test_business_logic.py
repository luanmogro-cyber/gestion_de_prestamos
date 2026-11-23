import pytest
import sqlite3
import os
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from backend.common.config import ConfigManager
from backend.database.db_manager import DatabaseManager, DiskFullError, PermissionDeniedError
from backend.database.models import initialize_database
from backend.business.auth_service import AuthService
from backend.business.client_service import ClientService
from backend.business.loan_calculator import LoanCalculator
from backend.business.payment_service import PaymentService

@pytest.fixture
def temp_env(tmp_path):
    """Configura un entorno aislado en /tmp para pruebas unitarias."""
    db_file = tmp_path / "test_prestamos.db"
    config = ConfigManager()
    
    # Redirigir temporalmente la ruta de base de datos
    db_mgr = DatabaseManager(db_file)
    initialize_database(db_mgr)
    
    auth_srv = AuthService(db_mgr)
    client_srv = ClientService(db_mgr)
    calc_srv = LoanCalculator(db_mgr)
    pay_srv = PaymentService(db_mgr)
    
    yield {
        "db": db_mgr,
        "auth": auth_srv,
        "clients": client_srv,
        "calc": calc_srv,
        "payments": pay_srv,
        "tmp_dir": tmp_path
    }

# --------------------------------------------------------------------------
# 1. CASO DE ACEPTACIÓN: 10.000.000 AL 18% ANUAL A 12 MESES MÉTODO FRANCÉS
# --------------------------------------------------------------------------
def test_acceptance_case_french_10m(temp_env):
    calc = temp_env["calc"]
    principal = Decimal("10000000.00")
    rate = Decimal("18.00")
    installments = 12
    periodicity = "mensual"
    
    sim = calc.simulate_loan(
        principal=principal,
        annual_interest_rate=rate,
        installments_count=installments,
        periodicity=periodicity,
        method="frances",
        disbursement_date=date(2026, 1, 15)
    )
    
    cronograma = sim["cronograma"]
    resumen = sim["resumen"]
    
    assert len(cronograma) == 12
    
    # Cuota fija francesa aproximada: 916,799.93
    first_cuota = cronograma[0]["cuota_total"]
    assert first_cuota == Decimal("916799.93")
    
    # La suma de todos los abonos a capital debe ser exactamente igual al principal
    total_capital_amortizado = sum(item["capital"] for item in cronograma)
    assert total_capital_amortizado == principal
    
    # El saldo remanente al final debe ser exactamente 0.00
    assert cronograma[-1]["saldo_remanente"] == Decimal("0.00")
    
    # El total pagado debe ser capital + intereses
    assert resumen["total_a_pagar"] == principal + resumen["total_intereses"]

# --------------------------------------------------------------------------
# 2. MÉTODO ALEMÁN: ABONO CONSTANTE A CAPITAL
# --------------------------------------------------------------------------
def test_german_amortization_constant_principal(temp_env):
    calc = temp_env["calc"]
    principal = Decimal("12000000.00")
    installments = 12
    
    sim = calc.simulate_loan(
        principal=principal,
        annual_interest_rate=Decimal("12.00"),
        installments_count=installments,
        periodicity="mensual",
        method="aleman",
        disbursement_date=date(2026, 1, 15)
    )
    
    cronograma = sim["cronograma"]
    expected_capital_per_quota = Decimal("1000000.00")
    
    # Cada cuota debe amortizar exactamente 1.000.000 a capital
    for item in cronograma:
        assert item["capital"] == expected_capital_per_quota
    
    # Los intereses deben ser estrictamente decrecientes
    intereses = [item["interes"] for item in cronograma]
    assert intereses == sorted(intereses, reverse=True)
    assert cronograma[-1]["saldo_remanente"] == Decimal("0.00")

# --------------------------------------------------------------------------
# 3. VERIFICACIÓN ESTRICTA DE TIPOS DECIMAL (PROHIBIDO FLOAT PARA DINERO)
# --------------------------------------------------------------------------
def test_strict_decimal_types(temp_env):
    calc = temp_env["calc"]
    sim = calc.simulate_loan(
        principal=Decimal("5000000.00"),
        annual_interest_rate=Decimal("20.00"),
        installments_count=6,
        periodicity="mensual",
        method="frances"
    )
    
    for c in sim["cronograma"]:
        assert isinstance(c["capital"], Decimal), "El capital debe ser Decimal"
        assert isinstance(c["interes"], Decimal), "El interés debe ser Decimal"
        assert isinstance(c["cuota_total"], Decimal), "La cuota total debe ser Decimal"
        assert isinstance(c["saldo_remanente"], Decimal), "El saldo remanente debe ser Decimal"

# --------------------------------------------------------------------------
# 4. AJUSTE DE FERIADOS Y FINES DE SEMANA
# --------------------------------------------------------------------------
def test_holidays_and_weekend_adjustment(temp_env):
    calc = temp_env["calc"]
    
    # Sábado 2026-05-16 -> Debe rodarse al Lunes 2026-05-18
    # Pero el 2026-05-18 es feriado (Ascensión en config) -> Debe rodarse al Martes 2026-05-19
    saturday_date = date(2026, 5, 16)
    adjusted = calc.adjust_for_weekends_and_holidays(saturday_date)
    assert adjusted == date(2026, 5, 19)
    assert adjusted.weekday() < 5  # Es día entre semana

# --------------------------------------------------------------------------
# 5. PRELACIÓN DE PAGOS: 1° MORA -> 2° INTERÉS -> 3° CAPITAL
# --------------------------------------------------------------------------
def test_payment_priority_order_strict(temp_env):
    client_srv = temp_env["clients"]
    calc = temp_env["calc"]
    pay_srv = temp_env["payments"]
    
    cid = client_srv.create_client({
        "doc_type": "CC", "doc_number": "100200300",
        "first_name": "Carlos", "last_name": "Mendoza",
        "birth_date": "1992-05-10", "phone": "3001234567",
        "email": "carlos@test.com", "monthly_income": "3000000"
    }, "admin")
    
    # Préstamo desembolsado en el pasado para inducir mora
    lid = calc.create_loan(
        client_id=cid,
        principal=Decimal("1000000.00"),
        annual_interest_rate=Decimal("12.00"),
        installments_count=2,
        periodicity="mensual",
        method="frances",
        commission_type="ninguna",
        commission_value=Decimal("0.00"),
        disbursement_date="2026-01-01",
        actor_username="admin"
    )
    
    # Pagar hoy (habrá mora acumulada sobre la cuota 1 vencida en febrero)
    pay_res = pay_srv.register_payment(
        loan_id=lid,
        amount=Decimal("200000.00"),
        payment_method="efectivo",
        payment_date="2026-03-01",
        actor_username="cajero"
    )
    
    # Verificar que se cobró primero la mora, luego el interés y el resto a capital
    assert pay_res["mora_applied"] > Decimal("0.00")
    assert pay_res["interest_applied"] > Decimal("0.00")
    assert pay_res["capital_applied"] > Decimal("0.00")
    assert pay_res["mora_applied"] + pay_res["interest_applied"] + pay_res["capital_applied"] == Decimal("200000.00")

# --------------------------------------------------------------------------
# 6. PAGO PARCIAL
# --------------------------------------------------------------------------
def test_partial_payment(temp_env):
    client_srv = temp_env["clients"]
    calc = temp_env["calc"]
    pay_srv = temp_env["payments"]
    
    cid = client_srv.create_client({
        "doc_type": "CC", "doc_number": "555666777",
        "first_name": "Ana", "last_name": "Gomez",
        "birth_date": "1988-10-15", "phone": "3109876543",
        "email": "ana@test.com", "monthly_income": "4500000"
    }, "admin")
    
    lid = calc.create_loan(
        client_id=cid, principal=Decimal("500000.00"),
        annual_interest_rate=Decimal("12.00"), installments_count=1,
        periodicity="mensual", method="frances",
        commission_type="ninguna", commission_value=Decimal("0.00"),
        disbursement_date="2026-06-01", actor_username="admin"
    )
    
    # Pago parcial pequeño de $10.000
    res = pay_srv.register_payment(
        loan_id=lid, amount=Decimal("10000.00"), payment_method="efectivo",
        payment_date="2026-06-05", actor_username="cajero"
    )
    
    assert res["new_loan_status"] == "activo"
    affected = res["affected_installments"][0]
    assert affected["status"] == "parcial"

# --------------------------------------------------------------------------
# 7. PREPAGO QUE CUBRE MÚLTIPLES CUOTAS
# --------------------------------------------------------------------------
def test_prepayment_multiple_installments(temp_env):
    client_srv = temp_env["clients"]
    calc = temp_env["calc"]
    pay_srv = temp_env["payments"]
    
    cid = client_srv.create_client({
        "doc_type": "CC", "doc_number": "999888777",
        "first_name": "Pedro", "last_name": "Picapiedra",
        "birth_date": "1985-01-01", "phone": "3123456789",
        "email": "pedro@test.com", "monthly_income": "5000000"
    }, "admin")
    
    lid = calc.create_loan(
        client_id=cid, principal=Decimal("200000.00"),
        annual_interest_rate=Decimal("10.00"), installments_count=2,
        periodicity="mensual", method="frances",
        commission_type="ninguna", commission_value=Decimal("0.00"),
        disbursement_date="2026-01-01", actor_username="admin"
    )
    
    # Pago que liquida completamente ambas cuotas ($250.000)
    res = pay_srv.register_payment(
        loan_id=lid, amount=Decimal("250000.00"), payment_method="transferencia",
        payment_date="2026-01-05", actor_username="cajero"
    )
    
    assert res["new_loan_status"] == "cancelado"
    for inst in res["affected_installments"]:
        assert inst["status"] == "pagada"

# --------------------------------------------------------------------------
# 8. CÁLCULO DE INTERÉS MORATORIO DIARIO
# --------------------------------------------------------------------------
def test_daily_late_fee_calculation(temp_env):
    calc = temp_env["calc"]
    capital = Decimal("1000000.00")
    # Tasa mora diaria 0.05% = 0.0005
    # En 10 días de retraso: 1.000.000 * 0.0005 * 10 = 5.000
    mora = calc.calculate_installment_late_fee(
        capital_pending=capital,
        due_date_str="2026-01-01",
        as_of_date_str="2026-01-11"
    )
    assert mora == Decimal("5000.00")

# --------------------------------------------------------------------------
# 9. BLOQUEO DE PRÉSTAMOS POR CLIENTE EN MORA SUPERIOR AL UMBRAL
# --------------------------------------------------------------------------
def test_blocking_delinquent_client_new_loan(temp_env):
    client_srv = temp_env["clients"]
    calc = temp_env["calc"]
    
    cid = client_srv.create_client({
        "doc_type": "CC", "doc_number": "444333222",
        "first_name": "Luis", "last_name": "Moroso",
        "birth_date": "1991-03-03", "phone": "3151112233",
        "email": "luis@test.com", "monthly_income": "2000000"
    }, "admin")
    
    # Crear préstamo con fecha muy antigua (más de 60 días de mora)
    calc.create_loan(
        client_id=cid, principal=Decimal("100000.00"),
        annual_interest_rate=Decimal("12.00"), installments_count=1,
        periodicity="mensual", method="frances",
        commission_type="ninguna", commission_value=Decimal("0.00"),
        disbursement_date="2025-01-01", actor_username="admin"
    )
    
    # Intentar otorgar nuevo préstamo al mismo cliente debe fallar
    with pytest.raises(ValueError, match="El cliente tiene cuotas en mora"):
        calc.create_loan(
            client_id=cid, principal=Decimal("500000.00"),
            annual_interest_rate=Decimal("12.00"), installments_count=3,
            periodicity="mensual", method="frances",
            commission_type="ninguna", commission_value=Decimal("0.00"),
            disbursement_date="2026-01-01", actor_username="admin"
        )

# --------------------------------------------------------------------------
# 10. REGLAS DE VALIDACIÓN DE CLIENTES
# --------------------------------------------------------------------------
def test_client_validation_rules(temp_env):
    client_srv = temp_env["clients"]
    
    # Menor de edad
    with pytest.raises(ValueError, match="mayor de edad"):
        client_srv.create_client({
            "doc_type": "TI", "doc_number": "111222333",
            "first_name": "Joven", "last_name": "Menor",
            "birth_date": "2015-01-01", "phone": "3001112233",
            "email": "joven@test.com", "monthly_income": "1000000"
        }, "admin")
        
    # Email inválido
    with pytest.raises(ValueError, match="correo electrónico"):
        client_srv.create_client({
            "doc_type": "CC", "doc_number": "111222334",
            "first_name": "Mario", "last_name": "Bros",
            "birth_date": "1990-01-01", "phone": "3001112233",
            "email": "correo_invalido_sin_arroba", "monthly_income": "1000000"
        }, "admin")

    # Ingresos mensuales menores o iguales a cero
    with pytest.raises(ValueError, match="mayores a cero"):
        client_srv.create_client({
            "doc_type": "CC", "doc_number": "111222335",
            "first_name": "Luigi", "last_name": "Bros",
            "birth_date": "1990-01-01", "phone": "3001112233",
            "email": "luigi@test.com", "monthly_income": "-500"
        }, "admin")

# --------------------------------------------------------------------------
# 11. AUTENTICACIÓN CON BCRYPT Y CONTROL DE ROLES
# --------------------------------------------------------------------------
def test_bcrypt_hashing_and_auth(temp_env):
    auth_srv = temp_env["auth"]
    
    # Admin por defecto (admin / admin1234)
    user = auth_srv.authenticate("admin", "admin1234")
    assert user is not None
    assert user["role"] == "Administrador"
    
    # Password incorrecta
    bad = auth_srv.authenticate("admin", "password_incorrecta")
    assert bad is None
    
    # Crear cajero y autenticar
    auth_srv.create_user("cajero_test", "cajero_pass_123", "Cajero Prueba", "Cajero", "admin")
    cajero = auth_srv.authenticate("cajero_test", "cajero_pass_123")
    assert cajero is not None
    assert cajero["role"] == "Cajero"

# --------------------------------------------------------------------------
# 12. RESPALDOS Y RESTAURACIÓN DE BASE DE DATOS
# --------------------------------------------------------------------------
def test_database_backup_and_restore_integrity(temp_env):
    db_mgr = temp_env["db"]
    tmp_dir = temp_env["tmp_dir"]
    
    backup_path = db_mgr.create_backup(custom_dest_dir=tmp_dir / "backups")
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0
    
    # Restaurar y verificar que la base de datos sigue operativa
    db_mgr.restore_backup(backup_path)
    with db_mgr.connection(exclusive_lock=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        assert cursor.fetchone()["cnt"] >= 1

# --------------------------------------------------------------------------
# 13. TOLERANCIA A FALLOS EN SISTEMA DE ARCHIVOS (SO-10)
# --------------------------------------------------------------------------
def test_filesystem_error_handling_so10(temp_env):
    db_mgr = temp_env["db"]
    
    # Simular error ENOSPC (disco lleno)
    err_enospc = OSError(28, "No space left on device")
    with pytest.raises(DiskFullError, match="No hay espacio suficiente en el disco"):
        db_mgr._handle_fs_error(err_enospc, "Escritura de prueba")
        
    # Simular error EACCES (permiso denegado)
    err_eacces = OSError(13, "Permission denied")
    with pytest.raises(PermissionDeniedError, match="Permiso denegado"):
        db_mgr._handle_fs_error(err_eacces, "Acceso a directorio protegido")


