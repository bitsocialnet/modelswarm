export function communityHttpsLink(value: unknown): { href: string; hostname: string } | null {
  if (typeof value !== 'string' || !value.startsWith('https://')) return null;

  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.hash) return null;
    const hostname = url.hostname.replace(/\.$/, '');
    if (hostname === 'localhost' || hostname.endsWith('.localhost')) return null;

    // Browsers normalize legacy IPv4 spellings that the signed source policy treats as DNS names.
    const rawHostname = value.slice('https://'.length).split(/[/:?#]/, 1)[0];
    if (/^(?:[0-9]+\.){3}[0-9]+$/.test(url.hostname) && rawHostname !== url.hostname) return null;
    return { href: url.href, hostname: url.hostname };
  } catch {
    return null;
  }
}

export function communityTorrentLink(value: unknown) {
  if (typeof value !== 'string' || !value.endsWith('.torrent')) return null;
  return /^\.\/(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*\/)+[0-9a-f]{64}\.torrent$/.test(value) ? value : null;
}
