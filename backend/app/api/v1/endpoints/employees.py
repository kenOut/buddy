from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDepartmentUpdate,
    EmployeeRead,
    EmployeeStatusUpdate,
)
from app.schemas.mission import MissionAssignmentRead
from app.services import department_service, employee_service, mission_service

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeRead])
async def list_employees(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await employee_service.list_employees(db, department_id)


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(employee_id: str, db: AsyncSession = Depends(get_db)):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


@router.post("", response_model=EmployeeRead, status_code=201)
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    return await employee_service.create_employee(db, payload)


@router.patch("/{employee_id}/status", response_model=EmployeeRead)
async def update_employee_status(
    employee_id: str, payload: EmployeeStatusUpdate, db: AsyncSession = Depends(get_db)
):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await employee_service.update_employee_status(db, employee, payload.status)


@router.patch("/{employee_id}/department", response_model=EmployeeRead)
async def update_employee_department(
    employee_id: str, payload: EmployeeDepartmentUpdate, db: AsyncSession = Depends(get_db)
):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if payload.department_id is not None:
        department = await department_service.get_department(db, payload.department_id)
        if department is None:
            raise HTTPException(status_code=404, detail="Department not found")

    return await employee_service.update_employee_department(db, employee, payload.department_id)


@router.get("/{employee_id}/missions", response_model=list[MissionAssignmentRead])
async def get_employee_missions(employee_id: str, db: AsyncSession = Depends(get_db)):
    assignments = await mission_service.list_assignments_for_employee(db, employee_id)
    return assignments
