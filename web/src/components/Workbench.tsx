"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info";

// 颜色只用于表达状态，不再作为装饰。
// 规则：绿色=正常/已完成，琥珀=待处理，红色=需要立刻注意，其余一律中性灰。
const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-zinc-100 text-zinc-600",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-700",
  danger: "bg-red-50 text-red-600",
  info: "bg-sky-50 text-sky-700",
};

function toneTextClass(tone?: Tone) {
  if (tone === "danger") return "text-red-600";
  if (tone === "warning") return "text-amber-600";
  if (tone === "success") return "text-emerald-600";
  return "text-zinc-900";
}

// 页头：紧凑一行。标题最大，说明只留一行小字，操作按钮靠右。
export function PageIntro({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-zinc-200 pb-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{title}</h1>
          <Chip>{eyebrow}</Chip>
        </div>
        {description ? <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function PrimaryLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700"
    >
      {children}
    </Link>
  );
}

export function SecondaryLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50 hover:text-zinc-900"
    >
      {children}
    </Link>
  );
}

// 一级卡片：细分隔线替代投影与嵌套色块，能少一个框就少一个框。
export function SurfaceCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-zinc-200 bg-white ${className ?? ""}`}>
      {title ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
            {description ? <p className="mt-0.5 text-xs text-zinc-500">{description}</p> : null}
          </div>
          {action}
        </div>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}

// 指标带：一条边框内的分隔列，替代 N 张各自成框的指标卡。
const STAT_STRIP_COLS: Record<number, string> = {
  2: "grid-cols-2",
  3: "grid-cols-2 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
  6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
};

export function StatStrip({
  items,
  columns = 4,
}: {
  items: Array<{ label: string; value: string; hint?: string; tone?: Tone }>;
  columns?: 2 | 3 | 4 | 5 | 6;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
      {/* 负外边距 + 容器裁切：让最外圈的右/下分隔线被剪掉，任意列数都不用逐格判断边框。 */}
      <div className={`-mb-px -mr-px grid ${STAT_STRIP_COLS[columns] ?? STAT_STRIP_COLS[4]}`}>
        {items.map((item, index) => (
          <div key={`${item.label}-${index}`} className="border-b border-r border-zinc-200 px-4 py-3">
            <div className="text-xs text-zinc-500">{item.label}</div>
            <div className={`mt-1 text-lg font-semibold tabular-nums ${toneTextClass(item.tone)}`}>{item.value}</div>
            {item.hint ? <div className="mt-0.5 truncate text-xs text-zinc-400">{item.hint}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

// 徽标：小圆角、低饱和。用于标签与筛选。
export function Chip({
  children,
  tone = "neutral",
  active = false,
  onClick,
}: {
  children: ReactNode;
  tone?: Tone;
  active?: boolean;
  onClick?: () => void;
}) {
  const base = "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition";
  if (!onClick) {
    return <span className={`${base} ${TONE_CLASS[tone]}`}>{children}</span>;
  }
  const interactive = active
    ? "bg-zinc-900 text-white"
    : `${TONE_CLASS[tone]} hover:brightness-95`;
  return (
    <button type="button" onClick={onClick} className={`${base} ${interactive}`}>
      {children}
    </button>
  );
}

export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}>{children}</span>;
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-200 px-4 py-6 text-center text-xs text-zinc-400">
      {text}
    </div>
  );
}

export function ActionButton({
  children,
  onClick,
  disabled,
  tone = "primary",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "primary" | "secondary";
  type?: "button" | "submit";
}) {
  const toneClass =
    tone === "primary"
      ? "bg-zinc-900 text-white hover:bg-zinc-700"
      : "border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${toneClass}`}
    >
      {children}
    </button>
  );
}
