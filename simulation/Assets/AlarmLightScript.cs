using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AlarmLightScript : MonoBehaviour
{
    float time = 0f;
    float flash_interval = 0.5f;

    // Start is called before the first frame update
    void Start()
    {
        SocketClient connection = SocketClient.Instance;
        connection.HandleEvent("alarm", (string[] data) => {
            string time_int = data[0];

            float time = float.Parse(time_int);
            this.time = time;

            GetComponent<Light>().enabled = true;
        });
    }

    // Update is called once per frame
    void Update()
    {
        if (time > 0f) {
            time -= Time.deltaTime;
            GetComponent<Light>().enabled = (time % (2 * flash_interval) < flash_interval);
            if (time <= 0f) {
                GetComponent<Light>().enabled = false;
            }
        }
    }
}
