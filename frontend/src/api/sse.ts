type SseEvent = { event: string; data: any };

function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";

  for (const raw of parts) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    const dataRaw = dataLines.join("\n").trim();
    let data: any = dataRaw;
    try {
      data = dataRaw ? JSON.parse(dataRaw) : {};
    } catch {
      // keep raw text
    }
    events.push({ event, data });
  }
  return { events, rest };
}

export async function fetchEventStream(
  input: RequestInfo | URL,
  init: RequestInit,
  onEvent: (evt: SseEvent) => void,
) {
  const res = await fetch(input, init);
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `stream failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buf);
    buf = parsed.rest;
    for (const evt of parsed.events) onEvent(evt);
  }
}

