// Optional same-origin API proxy for hosts that expose only the frontend port.
const apiTarget = process.env.BANFEI_API_PROXY_TARGET?.replace(/\/$/, '');
if (apiTarget) {
  const url = new URL(apiTarget);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('BANFEI_API_PROXY_TARGET must be an HTTP(S) origin without credentials');
  }
}
const buildCpus = process.env.BANFEI_BUILD_CPUS ? Number(process.env.BANFEI_BUILD_CPUS) : undefined;
if (buildCpus !== undefined && (!Number.isInteger(buildCpus) || buildCpus < 1)) {
  throw new Error('BANFEI_BUILD_CPUS must be a positive integer');
}
export default {
  ...((buildCpus || apiTarget) ? {experimental: {
    ...(buildCpus ? {cpus: buildCpus} : {}),
    // Existing batch-profile requests allow up to 390 seconds.
    ...(apiTarget ? {proxyTimeout: 420_000} : {}),
  }} : {}),
  async rewrites() {
    return apiTarget ? [{source: '/api/:path*', destination: `${apiTarget}/:path*`}] : [];
  },
};
