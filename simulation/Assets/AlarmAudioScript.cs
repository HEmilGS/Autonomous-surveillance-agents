using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AlarmAudioScript : MonoBehaviour
{
    
    float time = 0f;
    float flash_interval = 0.5f;

    public AudioSource src;
    public AudioClip audio1;

    // Start is called before the first frame update
    void Start()
    {
        SocketClient connection = SocketClient.Instance;
        connection.HandleEvent("alarm", (string[] data) => {
            src.clip = audio1;
            src.Play();
        });
    }

    // Update is called once per frame
    void Update()
    {
        if (time > 0f) {
            time -= Time.deltaTime;
            if (time <= 0f) {
                GetComponent<AudioSource>().Stop();
            }
        }
    }
}
