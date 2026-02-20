import type { OAuthProvider } from "../../../../api";

export type SourceProvider =
  | "mock"
  | "github"
  | "gmail"
  | "outlook"
  | "forward"
  | "imap"
  | "rss"
  | "bilibili"
  | "x"
  | "douyin"
  | "xiaohongshu"
  | "weibo";

export type OAuthSourceProvider = OAuthProvider;

export type GithubConnectMode = "oauth" | "token";
