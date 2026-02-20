import React from "react";
import ReactMarkdown from "react-markdown";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { alpha, useTheme } from "@mui/material/styles";

import {
  AelinAction,
  AelinCitation,
  AelinToolStep,
} from "../../../api";
import {
  AELIN_EXPRESSION_META,
  AELIN_EXPRESSION_SRC,
  AELIN_LOGO_SRC,
  PLATFORM_META,
  type PlatformKey,
} from "../constants";
import {
  formatIsoTime,
  formatTime,
  hashString,
  initialsFromName,
  looksLikeMarkdown,
  normalizeAutoLinksForMarkdown,
  normalizeAccountKey,
  normalizeExpressionId,
  normalizePlatformName,
  resolveCitationPlatform,
  toolStepLabel,
  traceParallelLabel,
  traceParallelLane,
} from "../helpers";
import { normalizeTraceStep } from "../chatState";
import { cardsFromMessage, citationKey } from "../messageCards";
import type {
  ChatMessage,
  ResultCard,
} from "../types";
const TypingDots = React.memo(function TypingDots() {
  return (
    <Box
      sx={{
        display: "inline-flex",
        gap: 0.5,
        "@keyframes aelinTypingDot": {
          "0%, 70%, 100%": { opacity: 0.3, transform: "translateY(0)" },
          "35%": { opacity: 1, transform: "translateY(-4px)" },
        },
      }}
    >
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s infinite ease-in-out" }} />
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s 0.14s infinite ease-in-out" }} />
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s 0.28s infinite ease-in-out" }} />
    </Box>
  );
});

const AccountAvatar = React.memo(function AccountAvatar({
  name,
  src,
  size = 16,
}: {
  name: string;
  src?: string | null;
  size?: number;
}) {
  const safeName = name || "unknown";
  const initial = initialsFromName(safeName);
  const hue = hashString(safeName) % 360;
  return (
    <Avatar
      src={src || undefined}
      alt={safeName}
      sx={{
        width: size,
        height: size,
        fontSize: Math.max(9, Math.floor(size * 0.5)),
        fontWeight: 700,
        border: "1px solid rgba(255,255,255,0.72)",
        background: src
          ? "transparent"
          : `linear-gradient(135deg, hsla(${hue},78%,58%,0.96), hsla(${(hue + 36) % 360},76%,47%,0.94))`,
        color: "#fff",
        boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
      }}
    >
      {!src ? initial : null}
    </Avatar>
  );
});

const InlineSourceBadge = React.memo(function InlineSourceBadge({
  platform,
  account,
  avatarSrc,
}: {
  platform: PlatformKey;
  account?: string;
  avatarSrc?: string;
}) {
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  const accountLabel = (account || "").trim();
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.42,
        px: 0.72,
        py: 0.2,
        mx: 0.24,
        borderRadius: 999,
        border: "1px solid",
        borderColor: meta.border,
        bgcolor: meta.bg,
        color: meta.color,
        verticalAlign: "middle",
        fontSize: "0.78em",
        fontWeight: 700,
        lineHeight: 1.2,
        transition: "transform 160ms ease, box-shadow 180ms ease",
        "&:hover": {
          transform: "translateY(-1px)",
          boxShadow: `0 6px 14px ${alpha(meta.color, 0.2)}`,
        },
      }}
    >
      <PlatformGlyph platform={platform} size={13} />
      {accountLabel ? <AccountAvatar name={accountLabel} src={avatarSrc} size={15} /> : null}
      <span>{accountLabel || meta.label}</span>
    </Box>
  );
});

const PlatformGlyph = React.memo(function PlatformGlyph({ platform, size = 14 }: { platform: PlatformKey; size?: number }) {
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  if (platform === "bilibili") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4.2" y="6.7" width="15.6" height="12.2" rx="3" stroke={meta.color} strokeWidth="1.7" />
        <path d="M8.4 4.6L10.4 6.7M15.6 4.6L13.6 6.7" stroke={meta.color} strokeWidth="1.7" strokeLinecap="round" />
        <path d="M9.3 11.4h0.01M14.7 11.4h0.01" stroke={meta.color} strokeWidth="2.3" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "douyin") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M13 5.5v8.2a3.8 3.8 0 11-2.2-3.4V6.8c1.9.2 3.4-.2 4.8-1.3" stroke={meta.color} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "xiaohongshu") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.4" y="3.4" width="17.2" height="17.2" rx="5" stroke={meta.color} strokeWidth="1.6" />
        <path d="M7.4 15.2l3-3 2.6 2.6 3.5-3.6" stroke={meta.color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "weibo") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="11.3" cy="13.1" r="4.5" stroke={meta.color} strokeWidth="1.7" />
        <path d="M16.6 7.6c1.4.4 2.6 1.4 3.2 2.8M15 5.4c2.3.3 4.4 1.9 5.3 4" stroke={meta.color} strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10.2" cy="12.7" r="0.8" fill={meta.color} />
      </svg>
    );
  }
  if (platform === "x") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5 5l14 14M18.6 5.3L5.4 18.7" stroke={meta.color} strokeWidth="2.1" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "github") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 4.5a7.6 7.6 0 00-2.4 14.9v-2.7c-1.6.4-2.3-.7-2.5-1.3-.2-.5-.7-1.3-1.2-1.6-.4-.2-1-.8 0-.8.9 0 1.5.8 1.7 1.2 1 .1 1.6-.7 1.8-1.1.1-.8.4-1.3.8-1.6-2.8-.3-5.8-1.4-5.8-6.2 0-1.4.5-2.6 1.3-3.5-.1-.3-.6-1.6.1-3.3 0 0 1.1-.3 3.6 1.3a12 12 0 016.6 0c2.5-1.6 3.6-1.3 3.6-1.3.7 1.7.2 3 .1 3.3.8.9 1.3 2.1 1.3 3.5 0 4.8-3 5.9-5.8 6.2.5.4.9 1.2.9 2.4v3.4A7.6 7.6 0 0012 4.5z" fill={meta.color} />
      </svg>
    );
  }
  if (platform === "rss") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="6.2" cy="17.8" r="1.8" fill={meta.color} />
        <path d="M5 11.4a7.7 7.7 0 017.6 7.6M5 6a13 13 0 0113 13" stroke={meta.color} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "email") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.8" y="6.2" width="16.4" height="11.6" rx="2.3" stroke={meta.color} strokeWidth="1.6" />
        <path d="M4.8 7.4l7.2 5.3 7.2-5.3" stroke={meta.color} strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "web") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="8.2" stroke={meta.color} strokeWidth="1.6" />
        <path d="M4.8 12h14.4M12 4.8c2.1 2.1 3.2 4.6 3.2 7.2s-1.1 5.1-3.2 7.2m0-14.4C9.9 6.9 8.8 9.4 8.8 12s1.1 5.1 3.2 7.2" stroke={meta.color} strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke={meta.color} strokeWidth="1.7" />
      <path d="M7.7 12h8.6M12 7.7v8.6" stroke={meta.color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
});

const CitationPill = React.memo(function CitationPill({
  item,
  onOpen,
}: {
  item: AelinCitation;
  onOpen?: (item: AelinCitation) => void;
}) {
  const platform = resolveCitationPlatform(item);
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  return (
    <Box
      onClick={() => onOpen?.(item)}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.55,
        px: 0.72,
        py: 0.35,
        borderRadius: 999,
        border: "1px solid",
        borderColor: meta.border,
        bgcolor: meta.bg,
        color: meta.color,
        fontSize: "0.74rem",
        lineHeight: 1.2,
        transition: "transform 160ms ease, box-shadow 180ms ease, filter 180ms ease",
        boxShadow: "0 0 0 rgba(0,0,0,0)",
        cursor: onOpen ? "pointer" : "default",
        "&:hover": {
          transform: "translateY(-1px)",
          boxShadow: `0 8px 18px ${alpha(meta.color, 0.2)}`,
          filter: "saturate(1.08)",
        },
      }}
      title={`${item.source_label} | ${item.title}`}
    >
      <PlatformGlyph platform={platform} size={13} />
      <AccountAvatar name={item.sender || item.source_label} src={item.sender_avatar_url} size={16} />
      <Typography
        component="span"
        sx={{
          fontSize: "0.73rem",
          fontWeight: 700,
          lineHeight: 1,
          maxWidth: 88,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {item.sender || item.source_label}
      </Typography>
      <Typography component="span" sx={{ fontSize: "0.74rem", fontWeight: 700, lineHeight: 1 }}>
        {item.source_label}
      </Typography>
      <Typography component="span" sx={{ fontSize: "0.72rem", opacity: 0.78, lineHeight: 1 }}>
        {item.received_at.slice(5)}
      </Typography>
    </Box>
  );
});

const ToolTraceRow = React.memo(function ToolTraceRow({ steps }: { steps: AelinToolStep[] }) {
  const normalized = React.useMemo(() => {
    const rows = (steps || [])
      .map(normalizeTraceStep)
      .filter((it) => String(it.stage || "").trim().length > 0)
      .sort((a, b) => {
        const ta = Number(a.ts || 0);
        const tb = Number(b.ts || 0);
        if (ta > 0 && tb > 0 && ta !== tb) return ta - tb;
        if (ta > 0 && tb <= 0) return -1;
        if (ta <= 0 && tb > 0) return 1;
        return a.stage.localeCompare(b.stage);
      });
    return rows.slice(-64);
  }, [steps]);
  if (!normalized.length) return null;
  const parallelGroups = React.useMemo(() => {
    const bucket = new Map<string, { total: number; running: number; failed: number }>();
    for (const step of normalized) {
      const lane = traceParallelLane(step.stage);
      if (!lane) continue;
      const prev = bucket.get(lane) || { total: 0, running: 0, failed: 0 };
      prev.total += 1;
      if (step.status === "running") prev.running += 1;
      if (step.status === "failed") prev.failed += 1;
      bucket.set(lane, prev);
    }
    return Array.from(bucket.entries()).map(([lane, info]) => ({ lane, ...info }));
  }, [normalized]);
  return (
    <Stack spacing={0.4} sx={{ mb: 0.58, px: 0.2 }}>
      {parallelGroups.length ? (
        <Stack direction="row" spacing={0.45} flexWrap="wrap" useFlexGap>
          {parallelGroups.map((group) => {
            const busy = group.running > 0;
            const color = group.failed > 0 ? "#d1495b" : busy ? "#f4a261" : "#2a9d8f";
            const suffix = busy ? ` running ${group.running}` : group.failed ? ` failed ${group.failed}` : " done";
            return (
              <Chip
                key={group.lane}
                size="small"
                variant="outlined"
                label={`${traceParallelLabel(group.lane)} x${group.total}${suffix}`}
                sx={{
                  borderColor: alpha(color, 0.45),
                  color,
                  bgcolor: alpha(color, 0.1),
                  "& .MuiChip-label": { px: 0.8, fontSize: "0.66rem", fontWeight: 700 },
                }}
              />
            );
          })}
        </Stack>
      ) : null}

      <Stack spacing={0.34}>
        {normalized.map((step, idx) => {
          const done = step.status === "completed";
          const running = step.status === "running";
          const failed = step.status === "failed";
          const skipped = step.status === "skipped";
          const color = failed ? "#d1495b" : done ? "#2a9d8f" : skipped ? "#7c7c7c" : "#f4a261";
          return (
            <Box
              key={`${step.stage}-${idx}-${Number(step.ts || 0) || 0}`}
              title={failed ? step.detail || "" : ""}
              sx={{
                display: "grid",
                gridTemplateColumns: "10px 1fr",
                alignItems: "flex-start",
                gap: 0.58,
                px: 0.48,
                py: 0.32,
                borderRadius: 1,
                border: "1px solid",
                borderColor: alpha(color, 0.2),
                bgcolor: alpha(color, 0.06),
              }}
            >
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: color,
                  mt: 0.45,
                  ...(running
                    ? {
                        "@keyframes tracePulseDot": {
                          "0%, 100%": { transform: "scale(1)", opacity: 0.7 },
                          "50%": { transform: "scale(1.25)", opacity: 1 },
                        },
                        animation: "tracePulseDot 900ms ease-in-out infinite",
                      }
                    : {}),
                }}
              />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" sx={{ display: "block", fontWeight: 700, fontSize: "0.69rem", lineHeight: 1.2 }}>
                  {toolStepLabel(step.stage)}
                  {step.count ? ` ${step.count}` : ""}
                </Typography>
                {failed && step.detail ? (
                  <Typography
                    variant="caption"
                    color="error.main"
                    sx={{
                      display: "-webkit-box",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      lineHeight: 1.22,
                      fontSize: "0.64rem",
                      mt: 0.08,
                    }}
                  >
                    {step.detail}
                  </Typography>
                ) : null}
              </Box>
            </Box>
          );
        })}
      </Stack>
    </Stack>
  );
});

const ResultDeck = React.memo(function ResultDeck({ cards, pulse }: { cards: ResultCard[]; pulse?: boolean }) {
  if (!cards.length) return null;
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(176px, 1fr))",
        gap: 0.65,
        mb: 0.75,
        "@keyframes deckPulse": {
          "0%, 100%": { transform: "translateY(0)", boxShadow: "0 0 0 rgba(0,0,0,0)" },
          "50%": { transform: "translateY(-1px)", boxShadow: "0 10px 18px rgba(0,0,0,0.08)" },
        },
      }}
    >
      {cards.slice(0, 6).map((card) => (
        <Paper
          key={card.id}
          variant="outlined"
          sx={{
            px: 0.95,
            py: 0.72,
            borderRadius: 1.3,
            borderColor: alpha(card.accent, 0.42),
            bgcolor: alpha(card.accent, 0.08),
            animation: pulse ? "deckPulse 900ms ease-in-out 1" : "none",
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.3 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: alpha(card.accent, 0.95), lineHeight: 1.2 }}>
              {card.title}
            </Typography>
            <Box sx={{ color: alpha(card.accent, 0.9), display: "flex", alignItems: "center" }}>{card.icon}</Box>
          </Stack>
          <Typography variant="body2" sx={{ fontWeight: 800, lineHeight: 1.25 }}>
            {card.value}
          </Typography>
          {card.subtitle ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block", lineHeight: 1.35 }}>
              {card.subtitle}
            </Typography>
          ) : null}
        </Paper>
      ))}
    </Box>
  );
});

function renderRichMessageContent(content: string, resolveAvatarSrc?: (account: string) => string | undefined) {
  const renderTextWithLinks = (text: string, keyPrefix: string) => {
    const out: React.ReactNode[] = [];
    const mdRegex = /\[([^\]\n]{1,120})\]\((https?:\/\/[^\s)]+)\)/g;
    let mdLast = 0;
    let mdSeg = 0;
    let mdMatch: RegExpExecArray | null = null;

    const pushPlainUrls = (plain: string, plainKey: string) => {
      const urlRegex = /(https?:\/\/[^\s<>"')\]]+)/g;
      let last = 0;
      let seg = 0;
      let m: RegExpExecArray | null = null;
      while ((m = urlRegex.exec(plain)) !== null) {
        const start = m.index;
        const end = start + m[0].length;
        if (start > last) out.push(plain.slice(last, start));
        const href = m[0];
        out.push(
          <Box
            key={`${plainKey}-url-${seg}`}
            component="a"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            sx={{ color: "primary.main", textDecoration: "underline", textUnderlineOffset: "2px" }}
          >
            {href}
          </Box>
        );
        last = end;
        seg += 1;
      }
      if (last < plain.length) out.push(plain.slice(last));
    };

    while ((mdMatch = mdRegex.exec(text)) !== null) {
      const start = mdMatch.index;
      const end = start + mdMatch[0].length;
      if (start > mdLast) pushPlainUrls(text.slice(mdLast, start), `${keyPrefix}-plain-${mdSeg}`);
      const label = mdMatch[1];
      const href = mdMatch[2];
      out.push(
        <Box
          key={`${keyPrefix}-md-${mdSeg}`}
          component="a"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          sx={{ color: "primary.main", textDecoration: "underline", textUnderlineOffset: "2px" }}
        >
          {label}
        </Box>
      );
      mdLast = end;
      mdSeg += 1;
    }
    if (mdLast < text.length) pushPlainUrls(text.slice(mdLast), `${keyPrefix}-tail`);
    return out;
  };

  const lines = content.split("\n");
  return lines.map((line, lineIdx) => {
    const bulletMatch = line.match(
      /^(\s*[-*]\s*)?\[([^[\]\n]{1,24})\]\s*([^（\n]+?)(?:（([^）\n]{1,40})）)?(?:（([^）\n]{1,32})）)?(.*)$/
    );
    if (bulletMatch) {
      const prefix = bulletMatch[1] || "";
      const platform = normalizePlatformName(bulletMatch[2] || "");
      const title = (bulletMatch[3] || "").trim();
      const sender = (bulletMatch[4] || "").trim();
      const time = (bulletMatch[5] || "").trim();
      const tail = bulletMatch[6] || "";
      if (platform) {
        const avatarSrc = sender ? resolveAvatarSrc?.(sender) : undefined;
        const suffix = `${title ? ` ${title}` : ""}${time ? `（${time}）` : ""}${tail}`;
        return (
          <React.Fragment key={`line-${lineIdx}`}>
            {prefix}
            <InlineSourceBadge platform={platform} account={sender} avatarSrc={avatarSrc} />
            {renderTextWithLinks(suffix, `bullet-${lineIdx}`)}
            {lineIdx < lines.length - 1 ? <br /> : null}
          </React.Fragment>
        );
      }
    }

    const nodes: React.ReactNode[] = [];
    const regex = /\[([^[\]\n]{1,24})\](?:\s*@?([a-zA-Z0-9_\-.\u4e00-\u9fff]{2,40}))?/g;
    let last = 0;
    let match: RegExpExecArray | null = null;
    let seg = 0;
    while ((match = regex.exec(line)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      if (start > last) nodes.push(...renderTextWithLinks(line.slice(last, start), `line-${lineIdx}-seg-${seg}`));
      const platform = normalizePlatformName(match[1] || "");
      if (platform) {
        const account = (match[2] || "").trim();
        const shouldAt = account && match[0].includes("@");
        const label = shouldAt ? `@${account}` : account;
        const avatarSrc = account ? resolveAvatarSrc?.(account) : undefined;
        nodes.push(
          <InlineSourceBadge
            key={`badge-${lineIdx}-${seg}`}
            platform={platform}
            account={label}
            avatarSrc={avatarSrc}
          />
        );
      } else {
        nodes.push(...renderTextWithLinks(match[0], `line-${lineIdx}-raw-${seg}`));
      }
      last = end;
      seg += 1;
    }
    if (last < line.length) nodes.push(...renderTextWithLinks(line.slice(last), `line-${lineIdx}-tail`));
    return (
      <React.Fragment key={`line-${lineIdx}`}>
        {nodes}
        {lineIdx < lines.length - 1 ? <br /> : null}
      </React.Fragment>
    );
  });
}

export const MessageRow = React.memo(function MessageRow(props: {
  message: ChatMessage;
  isGroupStart: boolean;
  onActionClick: (action: AelinAction) => void;
  onCopy: (text: string) => void;
  onCitationOpen: (item: AelinCitation) => void;
  pulse?: boolean;
  streamBusy?: boolean;
}) {
  const { message, isGroupStart, onActionClick, onCopy, onCitationOpen, pulse, streamBusy = false } = props;
  const theme = useTheme();
  const isUser = message.role === "user";
  const expressionId = !isUser && !message.pending ? normalizeExpressionId(message.expression) : undefined;
  const [hovered, setHovered] = React.useState(false);
  const cards = React.useMemo(() => cardsFromMessage(message), [message]);
  const accountAvatarMap = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of message.citations || []) {
      if (!item.sender_avatar_url) continue;
      const senderKey = normalizeAccountKey(item.sender || "");
      if (senderKey) map.set(senderKey, item.sender_avatar_url);
    }
    return map;
  }, [message.citations]);
  const resolveAvatarSrc = React.useCallback(
    (account: string) => {
      const key = normalizeAccountKey(account);
      if (!key) return undefined;
      return accountAvatarMap.get(key);
    },
    [accountAvatarMap]
  );

  return (
    <Box
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      sx={{
        "@keyframes aelinMessageIn": {
          from: { opacity: 0, transform: "translateY(10px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 1.1,
        px: { xs: 1.2, md: 2.4 },
        py: isGroupStart ? 1.1 : 0.4,
        animation: "aelinMessageIn 220ms ease",
      }}
    >
      {!isUser ? (
        <Avatar
          src={AELIN_LOGO_SRC}
          sx={{
            width: 36,
            height: 36,
            borderRadius: 1.2,
            bgcolor: "transparent",
            border: "none",
            boxShadow: "none",
            opacity: isGroupStart ? 1 : 0,
          }}
          imgProps={{ style: { objectFit: "cover", objectPosition: "center 24%" } }}
        />
      ) : (
        <Box sx={{ width: 36, height: 36 }} />
      )}

      <Box sx={{ maxWidth: "78%", minWidth: 58 }}>
        {isGroupStart ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", px: 0.65, mb: 0.5, textAlign: isUser ? "right" : "left", fontSize: "0.8rem" }}
          >
            {formatTime(message.ts)}
          </Typography>
        ) : null}

        <Paper
          variant="outlined"
          sx={{
            px: 1.35,
            py: 1.05,
            borderRadius: 1.75,
            bgcolor: isUser
              ? alpha(theme.palette.text.primary, theme.palette.mode === "light" ? 0.06 : 0.18)
              : "background.paper",
            transition: "transform 180ms ease, box-shadow 200ms ease",
            boxShadow: hovered ? `0 10px 20px ${alpha(theme.palette.text.primary, 0.08)}` : "none",
            transform: hovered ? "translateY(-1px)" : "translateY(0)",
          }}
        >
          {!isUser ? <ToolTraceRow steps={message.tool_trace || []} /> : null}
          {!isUser ? <ResultDeck cards={cards} pulse={pulse} /> : null}
          {!isUser && expressionId ? (
            <Box sx={{ display: "flex", justifyContent: "flex-start", mb: message.content ? 0.72 : 0 }}>
              <Tooltip title={`${AELIN_EXPRESSION_META[expressionId].label} 路 ${AELIN_EXPRESSION_META[expressionId].usage}`}>
                <Box
                  component="img"
                  src={AELIN_EXPRESSION_SRC[expressionId]}
                  alt={AELIN_EXPRESSION_META[expressionId].label}
                  sx={{
                    width: { xs: 140, sm: 168 },
                    maxWidth: "74%",
                    height: "auto",
                    display: "block",
                    filter: "drop-shadow(0 6px 14px rgba(0,0,0,0.12))",
                  }}
                />
              </Tooltip>
            </Box>
          ) : null}
          {message.images?.length ? (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(132px, 1fr))",
                gap: 0.7,
                mb: message.content ? 0.85 : 0,
              }}
            >
              {message.images.map((img, idx) => (
                <Box
                  key={`${message.id}-img-${idx}`}
                  component="img"
                  src={img.data_url}
                  alt={img.name || `image-${idx + 1}`}
                  sx={{
                    width: "100%",
                    maxHeight: 180,
                    objectFit: "cover",
                    borderRadius: 1.1,
                    border: "1px solid",
                    borderColor: "divider",
                  }}
                />
              ))}
            </Box>
          ) : null}

          {message.pending ? (
            <Stack spacing={0.8}>
              <Stack direction="row" spacing={0.9} alignItems="center">
                <TypingDots />
                <Typography variant="body1" color="text.secondary" sx={{ fontSize: "0.98rem" }}>
                  Aelin 正在思考...
                </Typography>
                {streamBusy ? (
                  <Chip
                    size="small"
                    variant="outlined"
                    label="流式更新中"
                    sx={{ "& .MuiChip-label": { px: 0.75, fontSize: "0.66rem", fontWeight: 700 } }}
                  />
                ) : null}
              </Stack>
              <Box>
                <Skeleton variant="text" width="85%" height={20} />
                <Skeleton variant="text" width="92%" height={20} />
                <Skeleton variant="text" width="70%" height={20} />
              </Box>
            </Stack>
          ) : (
            <Box sx={{ wordBreak: "break-word", lineHeight: 1.72, fontSize: "1rem" }}>
              {looksLikeMarkdown(message.content) ? (
                <Box
                  sx={{
                    "& p": { m: 0, mb: 1.05, lineHeight: 1.74 },
                    "& p:last-of-type": { mb: 0 },
                    "& ul, & ol": { mt: 0.25, mb: 1.05, pl: 2.3 },
                    "& li": { mb: 0.4 },
                    "& pre": {
                      m: 0,
                      mt: 0.6,
                      p: 1,
                      borderRadius: 1.2,
                      bgcolor: alpha(theme.palette.text.primary, 0.06),
                      overflowX: "auto",
                    },
                    "& code": {
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                      fontSize: "0.86em",
                    },
                    "& blockquote": {
                      m: 0,
                      my: 0.8,
                      pl: 1.1,
                      borderLeft: "3px solid",
                      borderColor: alpha(theme.palette.primary.main, 0.38),
                      color: "text.secondary",
                    },
                  }}
                >
                  <ReactMarkdown
                    components={{
                      a: ({ ...props }) => (
                        <a
                          {...props}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: theme.palette.primary.main, textDecoration: "underline", textUnderlineOffset: "2px" }}
                        />
                      ),
                    }}
                  >
                    {normalizeAutoLinksForMarkdown(message.content)}
                  </ReactMarkdown>
                </Box>
              ) : (
                <Box sx={{ whiteSpace: "pre-wrap" }}>
                  {renderRichMessageContent(message.content, resolveAvatarSrc)}
                </Box>
              )}
            </Box>
          )}
        </Paper>

        {!!message.citations?.length && (
          <Stack spacing={0.52} sx={{ mt: 0.68, px: 0.3, width: "100%", maxWidth: "100%", overflow: "hidden" }}>
            {message.citations.slice(0, 4).map((item) => {
              const platform = resolveCitationPlatform(item);
              const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
              const snippet = message.citation_snippets?.[citationKey(item)] || "";
              return (
                <Paper
                  key={`${message.id}-${item.message_id}-${item.source}`}
                  variant="outlined"
                  onClick={() => onCitationOpen(item)}
                  sx={{
                    px: 0.62,
                    py: 0.52,
                    borderRadius: 1.05,
                    cursor: "pointer",
                    borderColor: alpha(meta.color, 0.4),
                    bgcolor: alpha(meta.color, 0.05),
                    width: "100%",
                    maxWidth: "100%",
                    overflow: "hidden",
                    transition: "transform 140ms ease, box-shadow 160ms ease",
                    "&:hover": {
                      transform: "translateY(-1px)",
                      boxShadow: `0 6px 12px ${alpha(meta.color, 0.18)}`,
                    },
                  }}
                >
                  <Stack direction="row" spacing={0.62} alignItems="center" sx={{ minWidth: 0 }}>
                    <PlatformGlyph platform={platform} size={13} />
                    <AccountAvatar name={item.sender || item.source_label} src={item.sender_avatar_url} size={16} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          display: "block",
                          fontWeight: 700,
                          color: meta.color,
                          lineHeight: 1.2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.title}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          display: "block",
                          lineHeight: 1.2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.sender} 路 {item.source_label} 路 {item.received_at.slice(5)}
                      </Typography>
                    </Box>
                    <Chip
                      size="small"
                      label={item.score.toFixed(1)}
                      sx={{
                        height: 18,
                        minWidth: 34,
                        flexShrink: 0,
                        border: "1px solid",
                        borderColor: alpha(meta.color, 0.45),
                        bgcolor: alpha(meta.color, 0.08),
                        color: meta.color,
                        "& .MuiChip-label": { px: 0.58, fontSize: "0.62rem", fontWeight: 800 },
                      }}
                    />
                  </Stack>
                  {snippet ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        mt: 0.38,
                        pl: 2.95,
                        display: "-webkit-box",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: "vertical",
                        lineHeight: 1.28,
                      }}
                    >
                      {snippet}
                    </Typography>
                  ) : null}
                </Paper>
              );
            })}
          </Stack>
        )}

        {!!message.actions?.length && (
          <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap sx={{ mt: 0.6, px: 0.45 }}>
            {message.actions
              .filter((action) => action.kind !== "confirm_track")
              .slice(0, 3)
              .map((action, idx) => (
              <Button
                key={`${message.id}-${action.kind}-${idx}`}
                size="small"
                variant="outlined"
                onClick={() => onActionClick(action)}
              >
                {action.title}
              </Button>
            ))}
          </Stack>
        )}

        {!message.pending ? (
          <Stack
            direction="row"
            justifyContent={isUser ? "flex-end" : "flex-start"}
            sx={{ mt: 0.2, px: 0.3, opacity: hovered ? 1 : 0, transition: "opacity 140ms ease" }}
          >
            <IconButton size="small" onClick={() => onCopy(message.content)}>
              <ContentCopyIcon sx={{ fontSize: 15 }} />
            </IconButton>
          </Stack>
        ) : null}
      </Box>
    </Box>
  );
});


