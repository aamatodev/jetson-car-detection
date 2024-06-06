# Car Detection with DeepStream 6.2 on Jetson Nano

This repository contains a Dockerfile to build a Docker container for performing car detection using DeepStream 6.2 on a Jetson Nano with JetPack 5.1.

## Prerequisites

- Jetson Nano with JetPack 5.1 installed
- Docker installed and configured for use with NVIDIA runtime
- DeepStream SDK 6.2 downloaded from the [NVIDIA website](https://developer.download.nvidia.com/assets/Deepstream/DeepStream_6.2/deepstream_sdk_v6.2.0_jetson.tbz2) (may require sign-in)

## Preparing the Repository

1. Download the DeepStream SDK 6.2 from the [NVIDIA website](https://developer.download.nvidia.com/assets/Deepstream/DeepStream_6.2/deepstream_sdk_v6.2.0_jetson.tbz2).
2. Place the downloaded file `deepstream_sdk_v6.2.0_jetson.tbz2` in the root folder of this repository.

## Building the Docker Image

To build the Docker image, navigate to the directory containing the Dockerfile and run the following command:

```sh
docker build -t aamatodev/car_detection_service .
```

## Running the Docker Container

To run the Docker container, use the following command:

```sh
docker run -it --rm --net=host --runtime nvidia aamatodev/car_detection_service
```

## Setting the Video Stream

Once the container is running, you need to set the video stream to perform object recognition. You can do this by making a POST request to the specified endpoint:

```sh
curl -X POST http://<host_ip>:5000/set-video-stream -d '{"url" : "<stream url e.g. rtmp://<stream_ip>/live/livestream>"}'
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


