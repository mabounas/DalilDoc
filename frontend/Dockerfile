FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

FROM node:20-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_KIOSK_MODE=true
ARG NEXT_PUBLIC_BORNE_ID=borne-01
# Cible du proxy /api (lue par next.config.mjs au build).
ARG API_INTERNAL_URL=http://api:8000
# Les variables NEXT_PUBLIC_* sont figées dans le bundle au moment du build.
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_KIOSK_MODE=$NEXT_PUBLIC_KIOSK_MODE NEXT_PUBLIC_BORNE_ID=$NEXT_PUBLIC_BORNE_ID API_INTERNAL_URL=$API_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
