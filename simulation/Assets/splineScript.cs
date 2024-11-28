using UnityEngine.Splines;
using UnityEngine;

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

public class Spline_script : MonoBehaviour
{
    public SplineContainer spline;
    public float speed = 1f;

    float distancePercentage = 0f;
    float splineLenght;


    private void Start()
    {
        splineLenght = spline.CalculateLength();
    }

    private void Update()
    {
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
}