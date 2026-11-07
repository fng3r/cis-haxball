export function isEngineV2Enabled() {
  return import.meta.env.VITE_ENABLE_ENGINE_V2 === 'true';
}
