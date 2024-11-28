using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;

public class CameraManager : MonoBehaviour
{
    public GameObject prefabToMonitor; // Assign your animated prefab asset here
    public float captureInterval = 5f; // Time interval in seconds between captures
    public int imageWidth = 800; // Resolution width of the captured image
    public int imageHeight = 600; // Resolution height of the captured image

    private List<RobotCameraController> robotControllers = new List<RobotCameraController>(); // Track prefab instances with cameras

    private void Start()
    {
    }

    private void Update()
    {
        // Check if new prefab instances exist in the scene
        foreach (var prefabInstance in GameObject.FindObjectsOfType<GameObject>())
        {
            if (prefabInstance.name.Contains(prefabToMonitor.name) && 
                prefabInstance.GetComponent<RobotCameraController>() == null)
            {
                // Add a camera to the instance if it doesn't already have one
                RobotCameraController controller = prefabInstance.AddComponent<RobotCameraController>();
                controller.Initialize(captureInterval, imageWidth, imageHeight);
                robotControllers.Add(controller);
            }
        }
    }
}

public class RobotCameraController : MonoBehaviour
{
    private float timer; // Timer for capturing images
    private float captureInterval;
    private int imageWidth;
    private int imageHeight;
    private string cameraName;

    public void Initialize(float captureInterval, int imageWidth, int imageHeight)
    {
        this.captureInterval = captureInterval;
        this.imageWidth = imageWidth;
        this.imageHeight = imageHeight;

        // Add a new Camera component to the scene, not as a child
        
        // assign a unique name to the camera using uuid
        cameraName = Guid.NewGuid().ToString();
        
        GameObject cameraObject = new GameObject(cameraName);

        // Match the prefab's position and rotation, with an offset for head level
        float headHeight = 1.0f; // Adjust this value based on the height of your prefab's "head"
        cameraObject.transform.position = gameObject.transform.position + (Vector3.up * headHeight); // Elevate to head level
        cameraObject.transform.rotation = gameObject.transform.rotation; // Match world rotation

        // Add the CameraFollower script to make the camera follow the prefab
        CameraFollower follower = cameraObject.AddComponent<CameraFollower>();
        follower.target = gameObject.transform;
        follower.heightOffset = headHeight;

        // Add a Camera component
        Camera fpCamera = cameraObject.AddComponent<Camera>();
        fpCamera.fieldOfView = 60; // Standard FOV, adjust as needed

        timer = captureInterval; // Initialize the timer
    }

    private void Update()
    {
        // Update timer
        timer -= Time.deltaTime;

        if (timer <= 0f)
        {
            CaptureImage();
            timer = captureInterval; // Reset timer
        }
    }

    private void CaptureImage()
    {
        // Create a RenderTexture for capturing the image
        Camera camera = GameObject.Find(cameraName).GetComponent<Camera>();
        RenderTexture renderTexture = new RenderTexture(imageWidth, imageHeight, 24);
        camera.targetTexture = renderTexture;

        // Render the camera's view to the RenderTexture
        RenderTexture.active = renderTexture;
        camera.Render();

        // Create a Texture2D to read pixels from the RenderTexture
        Texture2D texture = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);
        texture.ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
        texture.Apply();

        // Reset the camera's target texture
        camera.targetTexture = null;
        RenderTexture.active = null;
        Destroy(renderTexture);

        // Convert to bytes and send through socket
        byte[] imageBytes = texture.EncodeToPNG();
        Destroy(texture);

        // Convert bytes to base64 string
        string base64Image = Convert.ToBase64String(imageBytes);
        
        // Send through socket connection
        SocketClient.Instance.SendEvent("camera_capture", new string[] { cameraName, base64Image });

        // Debug.Log($"Image captured and sent for {gameObject.name}");
    }
}