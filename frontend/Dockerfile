# =============================================================================
# HADES frontend image (Linux). Builds the app; the dev override swaps CMD to
# `npm run dev` with source mounted for hot-reload.
# =============================================================================
FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

EXPOSE 5173
# Production default: serve the built assets. Dev override runs `npm run dev`.
CMD ["npm", "run", "preview"]
