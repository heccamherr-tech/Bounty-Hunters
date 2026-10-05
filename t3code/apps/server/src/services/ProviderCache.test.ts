import * as Duration from "effect/Duration";
import * as Effect from "effect/Effect";
import * as PubSub from "effect/PubSub";
import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_CAPABILITIES_TTL,
  DEFAULT_MODELS_TTL,
  makeProviderCache,
  type ProviderConfigChangeEvent,
} from "./ProviderCache.ts";

describe("ProviderCache", () => {
  it("has correct default TTLs according to specification (5m for models, 15m for capabilities)", () => {
    expect(Duration.toMinutes(DEFAULT_MODELS_TTL)).toBe(5);
    expect(Duration.toMinutes(DEFAULT_CAPABILITIES_TTL)).toBe(15);
  });

  it("caches provider model lists and tracks hit/miss metrics", async () => {
    await Effect.runPromise(
      Effect.gen(function* () {
        const cache = yield* makeProviderCache();
        const fetcher = vi.fn(() => Effect.succeed(["model-gpt-4o", "model-claude-3-5"]));

        // First call: Cache Miss
        const res1 = yield* cache.getModels("openai", fetcher);
        expect(res1).toEqual(["model-gpt-4o", "model-claude-3-5"]);
        expect(fetcher).toHaveBeenCalledTimes(1);

        // Second call: Cache Hit
        const res2 = yield* cache.getModels("openai", fetcher);
        expect(res2).toEqual(["model-gpt-4o", "model-claude-3-5"]);
        expect(fetcher).toHaveBeenCalledTimes(1); // Not called again

        const metrics = yield* cache.getMetrics();
        expect(metrics.models.hits).toBe(1);
        expect(metrics.models.misses).toBe(1);
        expect(metrics.models.hitRatio).toBe(0.5);
      }),
    );
  });

  it("caches provider capabilities queries and tracks hit/miss metrics", async () => {
    await Effect.runPromise(
      Effect.gen(function* () {
        const cache = yield* makeProviderCache();
        const fetcher = vi.fn(() => Effect.succeed({ sessionModelSwitch: "in-session" as const }));

        // First call: Cache Miss
        const cap1 = yield* cache.getCapabilities("anthropic", fetcher);
        expect(cap1).toEqual({ sessionModelSwitch: "in-session" });
        expect(fetcher).toHaveBeenCalledTimes(1);

        // Second call: Cache Hit
        const cap2 = yield* cache.getCapabilities("anthropic", fetcher);
        expect(cap2).toEqual({ sessionModelSwitch: "in-session" });
        expect(fetcher).toHaveBeenCalledTimes(1);

        const metrics = yield* cache.getMetrics();
        expect(metrics.capabilities.hits).toBe(1);
        expect(metrics.capabilities.misses).toBe(1);
        expect(metrics.capabilities.hitRatio).toBe(0.5);
        expect(metrics.total.hits).toBe(1);
        expect(metrics.total.misses).toBe(1);
      }),
    );
  });

  it("invalidates cache on manual invalidate and handleConfigChange", async () => {
    await Effect.runPromise(
      Effect.gen(function* () {
        const cache = yield* makeProviderCache();
        let counter = 0;
        const fetcher = () =>
          Effect.sync(() => {
            counter++;
            return [`model-v${counter}`];
          });

        const m1 = yield* cache.getModels("codex", fetcher);
        expect(m1).toEqual(["model-v1"]);

        // Invalidate specific instance
        yield* cache.invalidate("codex");

        const m2 = yield* cache.getModels("codex", fetcher);
        expect(m2).toEqual(["model-v2"]);

        // Invalidate via handleConfigChange event
        yield* cache.handleConfigChange({
          _tag: "ProviderConfigChanged",
          instanceId: "codex",
        });

        const m3 = yield* cache.getModels("codex", fetcher);
        expect(m3).toEqual(["model-v3"]);
      }),
    );
  });

  it("invalidates cache via Effect.Hub / PubSub subscription", async () => {
    await Effect.runPromise(
      Effect.scoped(
        Effect.gen(function* () {
          const cache = yield* makeProviderCache();
          const hub = yield* PubSub.unbounded<ProviderConfigChangeEvent>();

          // Subscribe to configuration changes
          yield* cache.subscribeToHub(hub);

          let counter = 0;
          const fetcher = () =>
            Effect.sync(() => {
              counter++;
              return { version: counter };
            });

          const c1 = yield* cache.getCapabilities("google", fetcher);
          expect(c1).toEqual({ version: 1 });

          // Cached hit
          const cCached = yield* cache.getCapabilities("google", fetcher);
          expect(cCached).toEqual({ version: 1 });

          // Publish config change to hub
          yield* PubSub.publish(hub, {
            _tag: "ProviderConfigChanged",
            instanceId: "google",
          });

          // Allow the event loop to deliver the event
          yield* Effect.sleep("20 millis");

          // Cache should have been invalidated
          const c2 = yield* cache.getCapabilities("google", fetcher);
          expect(c2).toEqual({ version: 2 });
        }),
      ),
    );
  });

  it("resets metrics correctly", async () => {
    await Effect.runPromise(
      Effect.gen(function* () {
        const cache = yield* makeProviderCache();
        yield* cache.getModels("p1", () => Effect.succeed(["m"]));
        yield* cache.getModels("p1", () => Effect.succeed(["m"]));

        const before = yield* cache.getMetrics();
        expect(before.total.hits).toBe(1);
        expect(before.total.misses).toBe(1);

        yield* cache.resetMetrics();
        const after = yield* cache.getMetrics();
        expect(after.total.hits).toBe(0);
        expect(after.total.misses).toBe(0);
        expect(after.total.hitRatio).toBe(0);
      }),
    );
  });
});
