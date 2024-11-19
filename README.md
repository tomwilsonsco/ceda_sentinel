# ceda_sentinel
Can use the docker image:

```bash
docker build . --no-cache --file .devcontainer/Dockerfile -t ceda
```
Docker image includes tk for plotting from within docker image using X11 forwarding. Therefore to run:
```bash
docker run --rm --gpus all -i -t -e DISPLAY -p 127.0.0.1:8888:8888 -w /app --mount type=bind,src="$(pwd)",target=/app ceda
```
