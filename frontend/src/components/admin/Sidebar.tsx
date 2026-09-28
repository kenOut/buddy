"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";

import { adminLogout } from "@/lib/adminAuth";

const links = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/employees", label: "Employees" },
  { href: "/admin/departments", label: "Departments" },
  { href: "/admin/missions", label: "Missions" },
  { href: "/admin/quests", label: "Quests" },
  { href: "/admin/analytics", label: "Analytics" },
];

function NavLink({
  href,
  label,
  active,
  className,
}: {
  href: string;
  label: string;
  active: boolean;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-buddy-primary/10 text-buddy-primary"
          : "text-buddy-muted hover:bg-buddy-border/40 hover:text-foreground",
        className
      )}
    >
      {label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const isActive = (link: (typeof links)[number]) =>
    link.exact ? pathname === link.href : pathname.startsWith(link.href);

  async function handleLogout() {
    await adminLogout();
    router.replace("/admin/login");
  }

  return (
    <>
      {/* Tablet and up: fixed left sidebar */}
      <aside className="hidden w-56 shrink-0 flex-col gap-1 border-r border-buddy-border bg-buddy-surface p-4 sm:flex">
        <Link href="/" className="mb-6 px-2 text-sm font-semibold tracking-tight text-buddy-primary">
          Buddy Admin
        </Link>
        {links.map((link) => (
          <NavLink key={link.href} href={link.href} label={link.label} active={isActive(link)} />
        ))}
        <button
          onClick={handleLogout}
          className="mt-auto whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm font-medium text-buddy-muted transition-colors hover:bg-buddy-border/40 hover:text-foreground"
        >
          Log out
        </button>
      </aside>

      {/* Mobile: sticky top bar, nav scrolls horizontally instead of being squeezed */}
      <header className="sticky top-0 z-10 flex flex-col gap-2 border-b border-buddy-border bg-buddy-surface px-4 py-3 sm:hidden">
        <div className="flex items-center justify-between">
          <Link href="/" className="text-sm font-semibold tracking-tight text-buddy-primary">
            Buddy Admin
          </Link>
          <button onClick={handleLogout} className="text-sm font-medium text-buddy-muted hover:text-foreground">
            Log out
          </button>
        </div>
        <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-0.5">
          {links.map((link) => (
            <NavLink
              key={link.href}
              href={link.href}
              label={link.label}
              active={isActive(link)}
              className="shrink-0"
            />
          ))}
        </nav>
      </header>
    </>
  );
}
