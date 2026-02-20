import React from "react";
import InsightsIcon from "@mui/icons-material/Insights";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";

import { AelinCitation } from "../../api";
import { ChatMessage, ResultCard } from "./types";

export function citationKey(item: Pick<AelinCitation, "message_id" | "source" | "title">): string {
  return `${item.message_id || 0}:${item.source || ""}:${item.title || ""}`.toLowerCase();
}

function parseScoreCards(text: string): ResultCard[] {
  const rows: ResultCard[] = [];
  const seen = new Set<string>();
  const regex = /([A-Za-z\u4e00-\u9fff]{1,24})?\s*(\d{2,3})\s*[-:：]\s*(\d{2,3})\s*([A-Za-z\u4e00-\u9fff]{1,24})?/g;
  let match: RegExpExecArray | null = null;
  while ((match = regex.exec(text)) !== null) {
    const left = (match[1] || "队伍A").trim();
    const right = (match[4] || "队伍B").trim();
    const a = Number(match[2]);
    const b = Number(match[3]);
    if (Number.isNaN(a) || Number.isNaN(b) || a < 40 || b < 40 || a > 200 || b > 200) continue;
    const id = `${left}-${a}-${b}-${right}`.toLowerCase();
    if (seen.has(id)) continue;
    seen.add(id);
    rows.push({
      id,
      title: `${left} vs ${right}`,
      value: `${a} : ${b}`,
      subtitle: a > b ? `${left} 暂时领先` : b > a ? `${right} 暂时领先` : "比分接近",
      accent: a > b ? "#e07a5f" : "#3f88c5",
      icon: <InsightsIcon sx={{ fontSize: 16 }} />,
    });
    if (rows.length >= 3) break;
  }
  return rows;
}

export function cardsFromMessage(message: ChatMessage): ResultCard[] {
  const cards: ResultCard[] = [];
  cards.push(...parseScoreCards(message.content || ""));
  for (const citation of message.citations || []) {
    if (cards.length >= 6) break;
    cards.push({
      id: `cite-${message.id}-${citation.message_id}-${citation.source}`,
      title: citation.source_label || citation.source,
      value: citation.title || "证据",
      subtitle: `${citation.sender || "unknown"} 路 ${citation.received_at.slice(5)}`,
      accent: "#4d6fff",
      icon: <TravelExploreIcon sx={{ fontSize: 16 }} />,
    });
  }
  return cards;
}
