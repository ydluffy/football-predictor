"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "总览" },
  { href: "/fixtures", label: "比赛" },
  { href: "/predictions", label: "预测" },
  { href: "/review", label: "复盘" },
  { href: "/odds", label: "赔率" },
  { href: "/setup", label: "系统" },
  { href: "/controller", label: "总控" },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center overflow-x-auto text-sm">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={
              active
                ? "shrink-0 border-b-2 border-zinc-900 px-2.5 py-2.5 font-medium text-zinc-900"
                : "shrink-0 border-b-2 border-transparent px-2.5 py-2.5 text-zinc-500 transition hover:text-zinc-900"
            }
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
