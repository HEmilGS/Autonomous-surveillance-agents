using UnityEngine;
using UnityEngine.Splines;
using System.Collections.Generic;

public class DroneManager : MonoBehaviour
{
    public GameObject dronePrefab;
    public SplineContainer spline;
    private float speed = 10f;
    private float pauseDuration = 8f; // Time to pause at the destination
    private float returnToSplineSpeed = 10f;

    private float distancePercentage = 0f;
    private float splineLength;

    private enum DroneState { FollowingSpline, MovingToDestination, Pausing, ReturningToSpline }
    private DroneState currentState = DroneState.FollowingSpline;

    private Movement currentMovement;
    private float pauseTimer = 0f;

    class Movement
    {
        public Vector3 destination;
        public Quaternion rotation;
        public string type;
    }

    private List<Movement> movements = new List<Movement>();

    private void Start()
    {
        Animator animator = dronePrefab.GetComponent<Animator>(); // Get the animator component

        animator.SetBool("isSleeping", false); // Set the isSleeping parameter to false to make the drone take off from the drone port
        animator.SetBool("isFlying", true); // Set the isFlying parameter to true to make the drone fly

        // Save the initial position and rotation of the drone itself
        Vector3 basePosition = dronePrefab.transform.position;
        Quaternion baseRotation = dronePrefab.transform.rotation;

        // Add to the movements list to take off the drone from the drone port, and move it to the first point of the spline path
        movements.Add(new Movement { destination = spline.EvaluatePosition(0f), rotation = Quaternion.identity, type = "move_to" });

        SocketClient connection = SocketClient.Instance;
        connection.HandleEvent("move_to", (string[] data) =>
        {
            float x = float.Parse(data[0]);
            float y = float.Parse(data[1]);
            float z = float.Parse(data[2]);

            float xrot = float.Parse(data[3]);
            float yrot = float.Parse(data[4]);
            float zrot = float.Parse(data[5]);

            Vector3 destination = new Vector3(x, y, z);
            Quaternion rotation = Quaternion.Euler(xrot, yrot + 90, zrot);

            movements.Add(new Movement { destination = destination, rotation = rotation, type = "move_to" });
        });

        connection.HandleEvent("return_to_base", (string[] data) =>
        {
            movements.Add(new Movement { destination = basePosition, rotation = baseRotation, type = "return_to_base" });
        });
    }

    private void MoveDroneSpline()
    {
        distancePercentage += speed * Time.deltaTime / splineLength;

        Vector3 currentPosition = spline.EvaluatePosition(distancePercentage);
        dronePrefab.transform.position = currentPosition;

        if (distancePercentage > 1f)
        {
            distancePercentage = 0f;
        }

        Vector3 nextPosition = spline.EvaluatePosition(distancePercentage + 0.05f);
        Vector3 direction = nextPosition - currentPosition;
        dronePrefab.transform.rotation = Quaternion.LookRotation(direction, dronePrefab.transform.up);
    }

    private void MoveToDestination()
    {
        if (dronePrefab.transform.position == currentMovement.destination)
        {
            // make sure the drone's rotation is correct
            dronePrefab.transform.rotation = currentMovement.rotation;

            SocketClient.Instance.SendEvent("drone_status_update", new string[] { "IDLE" });
            currentState = DroneState.Pausing;
            pauseTimer = pauseDuration;
        }else if (Vector3.Distance(dronePrefab.transform.position, currentMovement.destination) < 0.2f && currentMovement.type == "return_to_base") 
        {
            SocketClient.Instance.SendEvent("drone_status_update", new string[] { "BUSY" });
            animator.SetBool("isFlying", false); // Set the isSleeping parameter to true to make the drone land on the drone port
            animator.SetBool("isSleeping", true); // Set the isSleeping parameter to true to make the drone land on the drone port
        }
        else
        {
            dronePrefab.transform.position = Vector3.MoveTowards(
                dronePrefab.transform.position,
                currentMovement.destination,
                Time.deltaTime * speed
            );
        }
    }

    private void PauseAtDestination()
    {
        pauseTimer -= Time.deltaTime;
        if (pauseTimer <= 0f)
        {
            currentState = DroneState.ReturningToSpline;
            SocketClient.Instance.SendEvent("drone_status_update", new string[] { "BUSY" });
        }
    }

    private void ReturnToSpline()
    {
        Vector3 closestPointOnSpline = spline.EvaluatePosition(distancePercentage);
        if (Vector3.Distance(dronePrefab.transform.position, closestPointOnSpline) < 0.1f)
        {
            currentState = DroneState.FollowingSpline;
            SocketClient.Instance.SendEvent("drone_status_update", new string[] { "IDLE" });
            movements.RemoveAt(0);
        }
        else
        {
            dronePrefab.transform.position = Vector3.MoveTowards(
                dronePrefab.transform.position,
                closestPointOnSpline,
                Time.deltaTime * returnToSplineSpeed
            );
        }
    }

    private void Update()
    {
        Animator animator = dronePrefab.GetComponent<Animator>();
        
        switch (currentState)
        {
            case DroneState.FollowingSpline:
                if (movements.Count > 0)
                {
                    currentMovement = movements[0];
                    currentState = DroneState.MovingToDestination;
                }
                else
                {
                    animator.SetBool("isMoving", true); 
                    MoveDroneSpline();
                }
                break;

            case DroneState.MovingToDestination:
                animator.SetBool("isMoving", true);
                MoveToDestination();
                break;

            case DroneState.Pausing:
                animator.SetBool("isMoving", false);
                PauseAtDestination();
                break;

            case DroneState.ReturningToSpline:
                animator.SetBool("isMoving", true);
                ReturnToSpline();
                break;
        }
    }
}
