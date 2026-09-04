"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "总览" },
  { href: "/controller", label: "总控助手" },
  { href: "/fixtures", label: "比赛" },
  { href: "/predictions", label: "预测" },
  { href: "/review", label: "复盘" },
  { href: "/setup", label: "系统" },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap items-center gap-2 text-sm">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={
              active
                ? "rounded-full bg-zinc-900 px-3 py-1.5 font-medium text-white"
                : "rounded-full px-3 py-1.5 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
            }
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
