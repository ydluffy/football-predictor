export function normalizeName(s?: string | null) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

const COMP_ZH: Record<string, string> = {
  PL: "英超",
  PD: "西甲",
  SA: "意甲",
  BL1: "德甲",
  FL1: "法甲",
  CL: "欧冠",
  EL: "欧联",
  ECL: "欧协联",
  WC: "世界杯",
};

const STATUS_ZH: Record<string, string> = {
  SCHEDULED: "未开始",
  TIMED: "未开始",
  IN_PLAY: "进行中",
  PAUSED: "中场",
  FINISHED: "已结束",
  POSTPONED: "延期",
  SUSPENDED: "暂停",
  CANCELED: "取消",
  AWARDED: "判定",
};

const TEAM_ZH: Record<string, string> = {
  "arsenal": "阿森纳",
  "chelsea": "切尔西",
  "liverpool": "利物浦",
  "manchester city": "曼城",
  "manchester united": "曼联",
  "tottenham hotspur": "热刺",
  "newcastle united": "纽卡斯尔",
  "aston villa": "阿斯顿维拉",
  "west ham united": "西汉姆联",
  "brighton & hove albion": "布莱顿",
  "everton": "埃弗顿",
  "real madrid": "皇家马德里",
  "fc barcelona": "巴塞罗那",
  "barcelona": "巴塞罗那",
  "atletico madrid": "马德里竞技",
  "sevilla": "塞维利亚",
  "valencia": "瓦伦西亚",
  "athletic club": "毕尔巴鄂竞技",
  "real sociedad": "皇家社会",
  "juventus": "尤文图斯",
  "ac milan": "AC米兰",
  "inter": "国际米兰",
  "inter milan": "国际米兰",
  "as roma": "罗马",
  "napoli": "那不勒斯",
  "lazio": "拉齐奥",
  "atalanta": "亚特兰大",
  "bayern munich": "拜仁慕尼黑",
  "borussia dortmund": "多特蒙德",
  "rb leipzig": "莱比锡RB",
  "bayer leverkusen": "勒沃库森",
  "eintracht frankfurt": "法兰克福",
  "paris saint-germain": "巴黎圣日耳曼",
  "psg": "巴黎圣日耳曼",
  "olympique de marseille": "马赛",
  "as monaco": "摩纳哥",
  "olympique lyonnais": "里昂",
};

export function competitionNameZh(code?: string | null, fallbackName?: string | null) {
  const c = (code || "").toUpperCase();
  return COMP_ZH[c] || fallbackName || code || "-";
}

export function statusZh(status?: string | null) {
  const s = (status || "").toUpperCase();
  return STATUS_ZH[s] || status || "-";
}

export function teamNameZh(name?: string | null) {
  const n = normalizeName(name);
  return TEAM_ZH[n] || name || "-";
}

export function formatLocalTimeFromUtc(utcIso?: string | null, tz = "Asia/Shanghai") {
  if (!utcIso) return "-";
  const d = new Date(utcIso);
  const fmt = new Intl.DateTimeFormat("zh-CN", { timeZone: tz, hour: "2-digit", minute: "2-digit" });
  return fmt.format(d);
}

