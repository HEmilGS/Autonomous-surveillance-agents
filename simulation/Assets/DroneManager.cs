using UnityEngine.Splines;
using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

public class DroneManager : MonoBehaviour
{
    public GameObject dronePrefab;
    public SplineContainer spline;
    float distancePercentage = 0f;
    float splineLenght;
    public float speed = 1f;

    class Movement {
        public Vector3 destination;
        public string type;
    }

    private Movement[] movements = new Movement[0];

    private void Start(){
        // first we make the drone take off from its landing zone

        // dronePrefab.transform.position = spline.GetPoint(0); // set the drone to the starting point of the spline path

        splineLenght = spline.CalculateLength();

        SocketClient connection = SocketClient.Instance;
        
        connection.HandleEvent("move_to", (string[] data) => {
            // move the drone to the GameObject camera with the name data[0]
            // SocketClient.Instance.SendEvent("drone_status_update", new string[] { "BUSY" });

            string cameraId = data[0];

            foreach (var prefabInstance in GameObject.FindObjectsOfType<GameObject>()) {
                if (prefabInstance.name == cameraId) {
                    Vector3 destination = prefabInstance.transform.position;
                    // GameObject camera = GameObject.Find(data[0]);
                    // Vector3 destination = camera.transform.position;
                    Movement movement = new() {
                        destination = destination,
                        type = "move_to"
                    };
                }
            }

        });
    }

    private void MoveDroneSpline(){

        distancePercentage += speed * Time.deltaTime / splineLenght;

        Vector3 currentPosition = spline.EvaluatePosition(distancePercentage);
        transform.position = currentPosition;

        if (distancePercentage > 1f)
        {
            distancePercentage = 0f;
        }

        Vector3 nextPosition = spline.EvaluatePosition(distancePercentage + 0.05f);
        Vector3 direction = nextPosition - currentPosition;
        transform.rotation = Quaternion.LookRotation(direction, transform.up);

    }

    private void MoveDrone(){
        // switch between the two movement types, if the drone receives a move_to command, 
        // it will move to the destination, while it does not receive any command, 
        // it will follow the spline, if the drone arrives at the destination, it will 
        // remove the movement from the list and set the drone to idle state and 

        foreach (Movement movement in movements) {
            Animator animator = dronePrefab.GetComponent<Animator>();

            if (movement.type == "move_to") {
                if (dronePrefab.transform.position == movement.destination) {
                    List<Movement> newMovements = new List<Movement>();
                    foreach (Movement m in movements) {
                        if (m != movement) {
                            newMovements.Add(m);
                        }
                    }
                    movements = newMovements.ToArray();
                    SocketClient.Instance.SendEvent("drone_status_update", new string[] { "IDLE" });
                } else {
                    dronePrefab.transform.position = Vector3.MoveTowards(dronePrefab.transform.position, movement.destination, Time.deltaTime * 2f);
                }
            }
        }
    }

    void Update() {
        // switch between the two movement types, if the drone receives a move_to command, it will move to the destination, while it does not receive any command, it will follow the spline
        if (movements.Length > 0) {
            MoveDrone();
        } else {
            MoveDroneSpline();
        }
    }
}