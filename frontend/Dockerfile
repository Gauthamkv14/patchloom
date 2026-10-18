# Multi-stage build for PatchLoom Frontend
# Stage 1: Build production static bundle
# Pinned Node 22 LTS (v22.23.3 Alpine 3.21), active security support through April 2027
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS builder

WORKDIR /app

# Copy dependency manifests and install cleanly
COPY package.json package-lock.json ./
RUN npm ci

# Copy configuration and TypeScript/React source code
COPY tsconfig.json tsconfig.node.json vite.config.ts index.html ./
COPY src ./src

# Build production assets into /app/dist
RUN npm run build

# Stage 2: Serve via lean Alpine Nginx
# Pinned Nginx 1.30 Stable (1.30.6 Alpine 3.24), verified upstream on 2026-10-18
FROM nginx:1.30-alpine@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5

# Remove default boilerplate files
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy reverse-proxy Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Configure ownership and permissions for unprivileged non-root nginx user
RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx/conf.d

# Run as non-root user
USER nginx

EXPOSE 3000

# Periodic health check verifying web server availability
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
