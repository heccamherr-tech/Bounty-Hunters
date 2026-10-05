/**
 * ProviderCache - Response caching service with TTL and invalidation for Provider APIs.
 *
 * Implements:
 * - Effect.Cache-based model lists with 5-minute default TTL
 * - Effect.Cache-based capability queries with 15-minute default TTL
 * - Cache invalidation on provider configuration changes via Effect.Hub / PubSub subscription
 * - Cache hit/miss and ratio metrics tracking
 *
 * @module ProviderCache
 */
import * as Cache from "effect/Cache";
import * as Context from "effect/Context";
import * as Duration from "effect/Duration";
import * as Effect from "effect/Effect";
import * as Layer from "effect/Layer";
import * as Option from "effect/Option";
import * as PubSub from "effect/PubSub";
import * as Ref from "effect/Ref";
import type * as Scope from "effect/Scope";

export const DEFAULT_MODELS_TTL = Duration.minutes(5);
export const DEFAULT_CAPABILITIES_TTL = Duration.minutes(15);
export const DEFAULT_CAPACITY = 256;

export interface ProviderConfigChangeEvent {
  readonly _tag: "ProviderConfigChanged";
  readonly instanceId?: string;
}

export interface CacheMetricCounts {
  readonly hits: number;
  readonly misses: number;
  readonly hitRatio: number;
}

export interface ProviderCacheMetrics {
  readonly models: CacheMetricCounts;
  readonly capabilities: CacheMetricCounts;
  readonly total: CacheMetricCounts;
}

export interface ProviderCacheConfig {
  readonly modelsTtl?: Duration.DurationInput;
  readonly capabilitiesTtl?: Duration.DurationInput;
  readonly capacity?: number;
}

export interface ProviderCacheShape {
  /**
   * Retrieves provider models from cache or invokes fetcher, caching result with models TTL (default: 5m).
   */
  readonly getModels: <T>(
    instanceId: string,
    fetcher: () => Effect.Effect<T>,
  ) => Effect.Effect<T>;

  /**
   * Retrieves provider capabilities from cache or invokes fetcher, caching result with capabilities TTL (default: 15m).
   */
  readonly getCapabilities: <T>(
    instanceId: string,
    fetcher: () => Effect.Effect<T>,
  ) => Effect.Effect<T>;

  /**
   * Invalidates cached models and capabilities for a specific provider instance (or all if omitted).
   */
  readonly invalidate: (instanceId?: string) => Effect.Effect<void>;

  /**
   * Invalidates all cached provider models and capabilities.
   */
  readonly invalidateAll: () => Effect.Effect<void>;

  /**
   * Returns current cache hit/miss counts and ratios.
   */
  readonly getMetrics: () => Effect.Effect<ProviderCacheMetrics>;

  /**
   * Resets hit and miss counters to zero.
   */
  readonly resetMetrics: () => Effect.Effect<void>;

  /**
   * Handles a provider configuration change event by invalidating affected cache entries.
   */
  readonly handleConfigChange: (event: ProviderConfigChangeEvent) => Effect.Effect<void>;

  /**
   * Subscribes to an Effect.Hub / PubSub for provider config changes, invalidating cache automatically.
   */
  readonly subscribeToHub: (
    hub: PubSub.PubSub<ProviderConfigChangeEvent>,
  ) => Effect.Effect<void, never, Scope.Scope>;
}

const computeRatio = (hits: number, misses: number): number => {
  const total = hits + misses;
  return total === 0 ? 0 : Number((hits / total).toFixed(4));
};

export const makeProviderCache = (
  config?: ProviderCacheConfig,
): Effect.Effect<ProviderCacheShape> =>
  Effect.gen(function* () {
    const capacity = config?.capacity ?? DEFAULT_CAPACITY;
    const modelsTtl = config?.modelsTtl ? Duration.decode(config.modelsTtl) : DEFAULT_MODELS_TTL;
    const capabilitiesTtl = config?.capabilitiesTtl
      ? Duration.decode(config.capabilitiesTtl)
      : DEFAULT_CAPABILITIES_TTL;

    const modelsHitsRef = yield* Ref.make(0);
    const modelsMissesRef = yield* Ref.make(0);
    const capabilitiesHitsRef = yield* Ref.make(0);
    const capabilitiesMissesRef = yield* Ref.make(0);

    const modelsCache = yield* Cache.make({
      capacity,
      timeToLive: modelsTtl,
      lookup: (_id: string) => Effect.dieMessage("modelsCache lookup requires direct fetcher"),
    });

    const capabilitiesCache = yield* Cache.make({
      capacity,
      timeToLive: capabilitiesTtl,
      lookup: (_id: string) =>
        Effect.dieMessage("capabilitiesCache lookup requires direct fetcher"),
    });

    const getModels: ProviderCacheShape["getModels"] = <T>(
      instanceId: string,
      fetcher: () => Effect.Effect<T>,
    ) =>
      Effect.gen(function* () {
        const cached = yield* Cache.getOption(modelsCache, instanceId);
        if (Option.isSome(cached)) {
          yield* Ref.update(modelsHitsRef, (n) => n + 1);
          return cached.value as T;
        }

        yield* Ref.update(modelsMissesRef, (n) => n + 1);
        const fresh = yield* fetcher();
        yield* Cache.set(modelsCache, instanceId, fresh);
        return fresh;
      });

    const getCapabilities: ProviderCacheShape["getCapabilities"] = <T>(
      instanceId: string,
      fetcher: () => Effect.Effect<T>,
    ) =>
      Effect.gen(function* () {
        const cached = yield* Cache.getOption(capabilitiesCache, instanceId);
        if (Option.isSome(cached)) {
          yield* Ref.update(capabilitiesHitsRef, (n) => n + 1);
          return cached.value as T;
        }

        yield* Ref.update(capabilitiesMissesRef, (n) => n + 1);
        const fresh = yield* fetcher();
        yield* Cache.set(capabilitiesCache, instanceId, fresh);
        return fresh;
      });

    const invalidateAll = (): Effect.Effect<void> =>
      Effect.gen(function* () {
        yield* Cache.invalidateAll(modelsCache);
        yield* Cache.invalidateAll(capabilitiesCache);
      });

    const invalidate = (instanceId?: string): Effect.Effect<void> =>
      instanceId === undefined
        ? invalidateAll()
        : Effect.gen(function* () {
            yield* Cache.invalidate(modelsCache, instanceId);
            yield* Cache.invalidate(capabilitiesCache, instanceId);
          });

    const getMetrics = (): Effect.Effect<ProviderCacheMetrics> =>
      Effect.gen(function* () {
        const mHits = yield* Ref.get(modelsHitsRef);
        const mMisses = yield* Ref.get(modelsMissesRef);
        const cHits = yield* Ref.get(capabilitiesHitsRef);
        const cMisses = yield* Ref.get(capabilitiesMissesRef);

        const totalHits = mHits + cHits;
        const totalMisses = mMisses + cMisses;

        return {
          models: {
            hits: mHits,
            misses: mMisses,
            hitRatio: computeRatio(mHits, mMisses),
          },
          capabilities: {
            hits: cHits,
            misses: cMisses,
            hitRatio: computeRatio(cHits, cMisses),
          },
          total: {
            hits: totalHits,
            misses: totalMisses,
            hitRatio: computeRatio(totalHits, totalMisses),
          },
        };
      });

    const resetMetrics = (): Effect.Effect<void> =>
      Effect.gen(function* () {
        yield* Ref.set(modelsHitsRef, 0);
        yield* Ref.set(modelsMissesRef, 0);
        yield* Ref.set(capabilitiesHitsRef, 0);
        yield* Ref.set(capabilitiesMissesRef, 0);
      });

    const handleConfigChange = (event: ProviderConfigChangeEvent): Effect.Effect<void> =>
      event.instanceId ? invalidate(event.instanceId) : invalidateAll();

    const subscribeToHub = (
      hub: PubSub.PubSub<ProviderConfigChangeEvent>,
    ): Effect.Effect<void, never, Scope.Scope> =>
      Effect.gen(function* () {
        const subscription = yield* PubSub.subscribe(hub);
        yield* Effect.gen(function* () {
          while (true) {
            const event = yield* PubSub.take(subscription);
            yield* handleConfigChange(event);
          }
        }).pipe(Effect.forkScoped);
      });

    return {
      getModels,
      getCapabilities,
      invalidate,
      invalidateAll,
      getMetrics,
      resetMetrics,
      handleConfigChange,
      subscribeToHub,
    };
  });

export class ProviderCache extends Context.Service<ProviderCache, ProviderCacheShape>()(
  "t3/services/ProviderCache",
) {}

export const ProviderCacheLive = (config?: ProviderCacheConfig): Layer.Layer<ProviderCache> =>
  Layer.effect(ProviderCache, makeProviderCache(config));
