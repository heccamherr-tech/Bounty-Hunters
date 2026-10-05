import * as zlib from "node:zlib";
import * as Effect from "effect/Effect";
import { HttpServerRequest, HttpServerResponse } from "effect/unstable/http";
import { describe, expect, it } from "vitest";

import {
  COMPRESSION_THRESHOLD_BYTES,
  httpCompressionMiddleware,
  isCompressibleContentType,
  isLoopbackHostname,
  resolveDevRedirectUrl,
  selectCompressionEncoding,
} from "./http.ts";

describe("http dev routing", () => {
  it("treats localhost and loopback addresses as local", () => {
    expect(isLoopbackHostname("127.0.0.1")).toBe(true);
    expect(isLoopbackHostname("localhost")).toBe(true);
    expect(isLoopbackHostname("::1")).toBe(true);
    expect(isLoopbackHostname("[::1]")).toBe(true);
  });

  it("does not treat LAN addresses as local", () => {
    expect(isLoopbackHostname("192.168.86.35")).toBe(false);
    expect(isLoopbackHostname("10.0.0.24")).toBe(false);
    expect(isLoopbackHostname("example.local")).toBe(false);
  });

  it("preserves path and query when redirecting to the dev server", () => {
    const devUrl = new URL("http://127.0.0.1:5173/");
    const requestUrl = new URL("http://127.0.0.1:3774/pair?token=test-token");

    expect(resolveDevRedirectUrl(devUrl, requestUrl)).toBe(
      "http://127.0.0.1:5173/pair?token=test-token",
    );
  });
});

describe("http compression helpers", () => {
  it("selects brotli over gzip when both are accepted", () => {
    expect(selectCompressionEncoding("gzip, deflate, br")).toBe("br");
    expect(selectCompressionEncoding("br;q=1.0, gzip;q=0.8")).toBe("br");
    expect(selectCompressionEncoding("gzip, deflate")).toBe("gzip");
    expect(selectCompressionEncoding("gzip")).toBe("gzip");
    expect(selectCompressionEncoding("deflate")).toBe(null);
    expect(selectCompressionEncoding(undefined)).toBe(null);
  });

  it("identifies compressible content types correctly", () => {
    expect(isCompressibleContentType("text/plain")).toBe(true);
    expect(isCompressibleContentType("text/html; charset=utf-8")).toBe(true);
    expect(isCompressibleContentType("application/json")).toBe(true);
    expect(isCompressibleContentType("image/svg+xml")).toBe(true);
    expect(isCompressibleContentType(undefined)).toBe(true);

    expect(isCompressibleContentType("image/png")).toBe(false);
    expect(isCompressibleContentType("image/jpeg")).toBe(false);
    expect(isCompressibleContentType("image/webp")).toBe(false);
    expect(isCompressibleContentType("video/mp4")).toBe(false);
    expect(isCompressibleContentType("audio/mpeg")).toBe(false);
    expect(isCompressibleContentType("application/zip")).toBe(false);
    expect(isCompressibleContentType("application/gzip")).toBe(false);
    expect(isCompressibleContentType("font/woff2")).toBe(false);
  });
});

describe("httpCompressionMiddleware", () => {
  const runWithRequest = (
    requestHeaders: Record<string, string>,
    response: HttpServerResponse.HttpServerResponse,
  ) => {
    const mockRequest = HttpServerRequest.fromWeb(
      new Request("http://localhost:3774/test", { headers: requestHeaders }),
    );
    const app = Effect.succeed(response);
    const compressedApp = httpCompressionMiddleware(app);
    return Effect.runPromise(
      compressedApp.pipe(Effect.provideService(HttpServerRequest.HttpServerRequest, mockRequest)),
    );
  };

  it("compresses large responses (> 1KB) with gzip when accepted", async () => {
    const largeText = "A".repeat(COMPRESSION_THRESHOLD_BYTES + 500);
    const res = HttpServerResponse.text(largeText);
    const out = await runWithRequest({ "accept-encoding": "gzip" }, res);

    expect(out.headers["content-encoding"]).toBe("gzip");
    expect(out.headers["vary"]).toContain("Accept-Encoding");
    expect(out.body._tag).toBe("Uint8Array");
    if (out.body._tag === "Uint8Array" && out.body.body instanceof Uint8Array) {
      const decompressed = zlib.gunzipSync(out.body.body).toString("utf-8");
      expect(decompressed).toBe(largeText);
    }
  });

  it("compresses large responses (> 1KB) with brotli when accepted, preferring br over gzip", async () => {
    const largeJson = JSON.stringify({ data: "B".repeat(2000) });
    const res = HttpServerResponse.jsonUnsafe(JSON.parse(largeJson));
    const out = await runWithRequest({ "accept-encoding": "gzip, deflate, br" }, res);

    expect(out.headers["content-encoding"]).toBe("br");
    expect(out.headers["vary"]).toContain("Accept-Encoding");
    if (out.body._tag === "Uint8Array" && out.body.body instanceof Uint8Array) {
      const decompressed = zlib.brotliDecompressSync(out.body.body).toString("utf-8");
      expect(decompressed).toBe(largeJson);
    }
  });

  it("does not compress small responses (< 1KB)", async () => {
    const smallText = "Hello small world";
    const res = HttpServerResponse.text(smallText);
    const out = await runWithRequest({ "accept-encoding": "gzip, br" }, res);

    expect(out.headers["content-encoding"]).toBeUndefined();
  });

  it("does not compress already compressed content types", async () => {
    const binaryData = new Uint8Array(2000).fill(42);
    const res = HttpServerResponse.uint8Array(binaryData, { contentType: "image/png" });
    const out = await runWithRequest({ "accept-encoding": "gzip, br" }, res);

    expect(out.headers["content-encoding"]).toBeUndefined();
  });

  it("does not compress if Content-Encoding is already set", async () => {
    const largeText = "Z".repeat(2000);
    const res = HttpServerResponse.text(largeText).pipe(
      HttpServerResponse.setHeader("Content-Encoding", "identity"),
    );
    const out = await runWithRequest({ "accept-encoding": "gzip, br" }, res);

    expect(out.headers["content-encoding"]).toBe("identity");
  });
});

