FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Dev server behind Nginx TLS. For a production image: `npm run build` and serve /dist from Nginx.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
