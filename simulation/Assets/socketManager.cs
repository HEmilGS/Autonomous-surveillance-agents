using System;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public delegate void Handler(string[] data);

public class SocketClient : MonoBehaviour
{
    // Singleton instance
    private static SocketClient _instance;

    // Public accessor for the instance
    public static SocketClient Instance
    {
        get
        {
            if (_instance == null)
            {
                // Attempt to find an existing instance
                _instance = FindFirstObjectByType<SocketClient>();

                // If none exists, create a new one
                if (_instance == null)
                {
                    GameObject singletonObject = new GameObject("SocketClient");
                    _instance = singletonObject.AddComponent<SocketClient>();
                    DontDestroyOnLoad(singletonObject);
                }
            }
            return _instance;
        }
    }

    public class Event
    {
        public string type;
        public string data;
    }

    public class EventHandler
    {
        public Handler fx;
        public string eventType;
    }

    private TcpClient client;
    private NetworkStream stream;
    private Dictionary<string, List<Handler>> handlers;


    private void Awake()
    {
        // Ensure this is the only instance
        if (_instance != null && _instance != this)
        {
            Destroy(gameObject);
            return;
        }

        client = new TcpClient("localhost", 65432);
        stream = client.GetStream();

        handlers = new Dictionary<string, List<Handler>>();

        _instance = this;
        DontDestroyOnLoad(gameObject);
    }

    ~SocketClient() {
        stream.Close();
        client.Close();
    }

    public void HandleEvent(string evt, Handler fx)
    {
        if (!handlers.ContainsKey(evt))
        {
            handlers[evt] = new List<Handler>();
        }

        handlers[evt].Add(fx);

    }

    private StringBuilder receiveBuffer = new StringBuilder();

    void Update()
    {
        if (stream == null || !stream.DataAvailable) return;

        byte[] receivedBuffer = new byte[1024];
        int bytes = stream.Read(receivedBuffer, 0, receivedBuffer.Length);
        string chunk = Encoding.ASCII.GetString(receivedBuffer, 0, bytes);

        // Append the received chunk to the buffer
        receiveBuffer.Append(chunk);

        // Process all complete messages in the buffer
        while (true)
        {
            string bufferContent = receiveBuffer.ToString();
            int newlineIndex = bufferContent.IndexOf('\n');

            // If no complete message exists, wait for more data
            if (newlineIndex == -1) break;

            // Extract the message and remove it from the buffer
            string message = bufferContent.Substring(0, newlineIndex).Trim();
            receiveBuffer.Remove(0, newlineIndex + 1);

            // Process the message
            Debug.Log("[SM]: " + message);
            Event evt = JsonUtility.FromJson<Event>(message);

            if (handlers.TryGetValue(evt.type, out var registeredHandlers))
            {
                foreach (var handler in registeredHandlers)
                {
                    handler?.Invoke(evt.data.Split(",")); // Ensure the delegate is not null
                }
            }
        }
    }

    public void SendEvent(string type, string[] data)
    {
        if (stream == null) return;

        string jsonData = JsonUtility.ToJson(new Event
        {
            type = type,
            data = string.Join(",", data)
        });

        byte[] messageBytes = Encoding.ASCII.GetBytes(jsonData + "\n");
        stream.Write(messageBytes, 0, messageBytes.Length);
    }

}