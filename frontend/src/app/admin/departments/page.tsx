"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { NewDepartmentModal } from "@/components/admin/NewDepartmentModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department, Employee, Organization } from "@/lib/types";

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [showNewDepartment, setShowNewDepartment] = useState(false);

  useEffect(() => {
    api.get<Department[]>("/departments").then(setDepartments);
    api.get<Employee[]>("/employees").then(setEmployees);
    api.get<Organization[]>("/organizations").then((orgs) => setOrganizationId(orgs[0]?.id ?? null));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Departments</h1>
          <p className="mt-1 text-sm text-buddy-muted">Org structure at a glance.</p>
        </div>
        <Button disabled={!organizationId} onClick={() => setShowNewDepartment(true)}>
          New department
        </Button>
      </div>

      {showNewDepartment && organizationId && (
        <NewDepartmentModal
          organizationId={organizationId}
          onClose={() => setShowNewDepartment(false)}
          onCreated={(department) => setDepartments((prev) => [...prev, department])}
        />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {departments.map((department) => {
          const headcount = employees.filter((e) => e.department_id === department.id).length;
          return (
            <Link key={department.id} href={`/admin/departments/${department.id}`}>
              <Card className="transition-colors hover:border-buddy-primary/50">
                <p className="font-medium text-foreground">{department.name}</p>
                {department.description && (
                  <p className="mt-1 text-sm text-buddy-muted">{department.description}</p>
                )}
                <p className="mt-3 text-xs uppercase tracking-wide text-buddy-muted">
                  {headcount} {headcount === 1 ? "employee" : "employees"}
                </p>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
