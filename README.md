# Car Detection with DeepStream 6.2 on Jetson Nano

This repository contains a Dockerfile to build a Docker container for performing car detection using DeepStream 6.2 on a Jetson Nano with JetPack 5.1.

## Prerequisites

- Jetson Nano with JetPack 5.1 installed
- Docker installed and configured for use with NVIDIA runtime

## Building the Docker Image

To build the Docker image, navigate to the directory containing the Dockerfile and run the following command:

```sh
docker build -t aamato/ycd .
```

## Running the Docker Container

To run the Docker container, use the following command:

```sh
docker run -it --rm --net=host --runtime nvidia aamato/ycd:latest
```

## Setting the Video Stream

Once the container is running, you need to set the video stream to perform object recognition. You can do this by making a POST request to the specified endpoint:

```sh
curl -X POST http://10.100.5.241:5000/set-video-stream -d '{"url" : "rtmp://10.100.4.210/live/livestream"}'
```

## Viewing the RTSP Stream

The container will produce an RTSP stream showing the real-time object detection. You can view this stream at:

```
rtsp://<host_ip>:8554/ds-test
```

Replace `<host_ip>` with the IP address of your host machine.

## License

This project is licensed under the MIT License.

## Acknowledgments

- NVIDIA DeepStream SDK
- Jetson Nano Community

## Support

For any issues or questions, please open an issue on the GitHub repository.

---
