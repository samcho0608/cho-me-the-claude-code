# API Reference

## Authentication

All requests must include a valid JWT in the Authorization header.
The JWT payload must contain the `sub` claim and the `scope` claim.

Tokens are validated against the JWKS endpoint configured at startup.
If the ECDSA signature verification fails, the request is rejected with HTTP 401.

## Rate Limiting

Requests are subject to sliding-window rate limiting using the Token Bucket algorithm.
Burst capacity is controlled by the `burst_factor` configuration parameter.

The RateLimiter component enforces limits at the gateway layer before requests reach the upstream service.

## Caching

Responses are cached using a write-through strategy. The CacheManager invalidates entries when the backing store is updated.
TTL values are derived from the `Cache-Control` headers returned by the upstream.
