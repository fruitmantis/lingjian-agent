// The public HTTP port-80 entry always uses the same-origin API proxy.
const apiTarget = process.env.BANFEI_API_PROXY_TARGET?.replace(/\/$/, '');
const allowedDevOrigins = (process.env.BANFEI_IDENTITY_ORIGIN || '').split(',').filter(Boolean).map(value => new URL(value).hostname);
if (apiTarget) {
  const url = new URL(apiTarget);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || (!/^[0-9]+$/.test(url.port) || Number(url.port) < 1024 || Number(url.port) > 65535) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('BANFEI_API_PROXY_TARGET must use http://127.0.0.1 with an explicit unprivileged port');
  }
}
const buildCpus = process.env.BANFEI_BUILD_CPUS ? Number(process.env.BANFEI_BUILD_CPUS) : undefined;
if (buildCpus !== undefined && (!Number.isInteger(buildCpus) || buildCpus < 1)) {
  throw new Error('BANFEI_BUILD_CPUS must be a positive integer');
}
export default {
  ...(allowedDevOrigins.length ? {allowedDevOrigins} : {}),
  ...(buildCpus ? {experimental: {cpus: buildCpus}} : {}),
};
