import { AdminAuthGate } from "@/components/admin/AdminAuthGate";

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return <AdminAuthGate>{children}</AdminAuthGate>;
}
