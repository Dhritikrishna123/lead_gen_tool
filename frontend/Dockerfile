FROM nginx:alpine

# Copy the static HTML frontend
COPY index.html /usr/share/nginx/html/index.html

# Copy the optional public assets if they exist (Next.js remnants)
COPY public/ /usr/share/nginx/html/public/ 

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
