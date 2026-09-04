"use client";

import { PageIntro, PrimaryLink, SecondaryLink } from "@/components/Workbench";
import { ChatPanel } from "@/components/ChatPanel";

export default function ChatPage() {
  const quickPrompts = [
    "今天有什么比赛？",
    "给我今天五大联赛的胜平负概率，并列出关键因素",
    "预测今天两场比赛，并给出Top比分/大小球(2.5)/双方进球",
    "结合当前赔率，找出今天最值得关注的比赛",
  ];

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="助手工作页"
        title="把自然语言提问和系统动作放在一起"
        description="这里不是单纯聊天窗口，而是工作台里的解释层。你可以直接问今天的比赛、预测结论、赔率价值，也可以先执行导入，再让助手解释结果。"
        actions={
          <>
            <PrimaryLink href="/predictions">查看预测</PrimaryLink>
            <SecondaryLink href="/setup">系统巡检</SecondaryLink>
          </>
        }
      />
      <ChatPanel
        initialMessages={[
          {
            role: "assistant",
            content:
              "你好，我是你的 AI 球赛预测助手。\n\n你可以这样问我：\n- 今天有什么比赛？\n- 给我今天五大联赛的胜平负概率，并列出关键因素\n- 帮我预测今天两场比赛，并给出 Top 比分 / 大小球(2.5) / 双方进球\n- 拉取今天的赔率并跑预测（需要配置 API_FOOTBALL_KEY）\n\n提示：系统以北京时间（Asia/Shanghai）理解“今天/昨天/明天”。",
          },
        ]}
        quickPrompts={quickPrompts}
        rightTitle="快捷提问"
        rightDescription="直接点击填入输入框，再发送。"
      />
    </div>
  );
}

