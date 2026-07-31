import { describe, expect, it } from "vitest";
import { parseNdjsonChunk } from "./api.ts";
import type { StreamEvent } from "./api.ts";

const DONE = '{"event":"done"}';
const TOKEN = '{"event":"token","stage":"analyzing","text":"hello"}';

describe("parseNdjsonChunk", () => {
  it("reads a single complete line", () => {
    const [events, buffer] = parseNdjsonChunk("", `${DONE}\n`);
    expect(events).toEqual([{ event: "done" }]);
    expect(buffer).toBe("");
  });

  it("reads several events arriving in one chunk", () => {
    const [events, buffer] = parseNdjsonChunk("", `${TOKEN}\n${DONE}\n`);
    expect(events).toHaveLength(2);
    expect(events[0].event).toBe("token");
    expect(events[1].event).toBe("done");
    expect(buffer).toBe("");
  });

  it("holds back a partial line instead of parsing it", () => {
    const [events, buffer] = parseNdjsonChunk("", '{"event":"to');
    expect(events).toEqual([]);
    expect(buffer).toBe('{"event":"to');
  });

  it("joins an event split across two reads", () => {
    // The hazard this whole function exists for: a network read does not
    // land on a line boundary, so one JSON object arrives in two pieces.
    const half = Math.floor(TOKEN.length / 2);
    const [first, buffer] = parseNdjsonChunk("", TOKEN.slice(0, half));
    expect(first).toEqual([]);

    const [second, rest] = parseNdjsonChunk(buffer, `${TOKEN.slice(half)}\n`);
    expect(second).toHaveLength(1);
    expect((second[0] as { text: string }).text).toBe("hello");
    expect(rest).toBe("");
  });

  it("joins an event split across three reads", () => {
    let buffer = "";
    let collected: StreamEvent[] = [];
    for (const piece of [TOKEN.slice(0, 10), TOKEN.slice(10, 25), `${TOKEN.slice(25)}\n`]) {
      const [events, rest] = parseNdjsonChunk(buffer, piece);
      buffer = rest;
      collected = [...collected, ...events];
    }
    expect(collected).toHaveLength(1);
    expect(buffer).toBe("");
  });

  it("ignores blank lines", () => {
    const [events] = parseNdjsonChunk("", `\n${DONE}\n\n`);
    expect(events).toHaveLength(1);
  });

  it("keeps a trailing event without a newline in the buffer", () => {
    const [events, buffer] = parseNdjsonChunk("", `${TOKEN}\n${DONE}`);
    expect(events).toHaveLength(1);
    expect(buffer).toBe(DONE);
  });
});
