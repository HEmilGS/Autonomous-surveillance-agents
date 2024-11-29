using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AlarmAudioScript : MonoBehaviour
{
    float alarmDuration = 0f; // Timer for stopping audio
    float suspicious_activity_interval = 60f; // Time between suspicious man reappearances
    float suspicious_activity_time = 0f; // Timer for suspicious man movement
    int nextPosition = 0; // Index of the next position
    bool alarmTriggered = false; // Track if the alarm has been triggered

    public AudioSource src;
    public AudioClip audio1;

    public GameObject suspiciousMan;
    public Vector3[] positions; // Positions array

    // Start is called before the first frame update
    void Start()
    {
        // Define the positions
        positions = new Vector3[] {
            new Vector3(445.49f, 0f, 423.66f),
            new Vector3(520.5f, 0f, 287.12f),
            new Vector3(368.44f, 0f, 284.926f)
        };

        // Initialize suspicious man timer
        suspicious_activity_time = suspicious_activity_interval;

        // Handle server event for alarm
        SocketClient connection = SocketClient.Instance;
        connection.HandleEvent("alarm", (string[] data) =>
        {
            // Play the alarm audio
            src.clip = audio1;
            src.Play();

            // Hide the suspicious man when the alarm is triggered
            suspiciousMan.SetActive(false);

            // Start alarm timer
            alarmDuration = src.clip.length;

            // Mark alarm as triggered
            alarmTriggered = true;

            // Send alarm triggered event with timestamp
            connection.SendEvent("alarm_triggered", new string[] { System.DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") });
        });
    }

    // Update is called once per frame
    void Update()
    {
        // Manage the alarm audio timer
        if (alarmDuration > 0f)
        {
            alarmDuration -= Time.deltaTime;
            if (alarmDuration <= 0f)
            {
                src.Stop();
            }
        }

        // Manage suspicious man behavior based on alarm status
        if (alarmTriggered)
        {
            // Countdown to reappear the suspicious man
            suspicious_activity_time -= Time.deltaTime;

            if (suspicious_activity_time <= 0f)
            {
                // Place the suspicious man at the next position
                suspiciousMan.transform.position = positions[nextPosition];
                suspiciousMan.SetActive(true);

                // Send suspicious activity event with timestamp and position
                SocketClient.Instance.SendEvent("suspicious_activity_started", new string[] { 
                    System.DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                });

                // Update the next position
                nextPosition = (nextPosition + 1) % positions.Length;

                // Reset the timer
                suspicious_activity_time = suspicious_activity_interval;

                // Reset the alarm state
                alarmTriggered = false; // Suspicious man shouldn't move again until the next alarm
            }
        }
    }
}
