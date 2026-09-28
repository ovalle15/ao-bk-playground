const axios = require('axios')
const dotenv = require('dotenv')

dotenv.config()

const nasaApiUrl = process.env.NASA_API_URL || 'https://api.nasa.gov/planetary/apod'

/** Image Collection Transactions */

const getImage = async(req, response) => {
  console.log('**** GETTING IMAGE ****')

  const requestedDate = req.query.date;

  if (requestedDate && !isValidApodDate(requestedDate)) {
    return response.status(400).json({
      success: false,
      error: 'Date must be between 1995-06-16 and today'
    });
  }

  try {
    const res = await axios.get(nasaApiUrl, {
      params: {
        api_key: process.env.API_TOKEN,
        thumbs: true,
        ...(requestedDate && { date: requestedDate })
      }
    });
    const nasaImage = {
      title: res.data.title,
      date: res.data.date,
      explanation: res.data.explanation,
      attribution: res.data.copyright || 'NASA',
      mediaType: res.data.media_type,
      mediaUrl: res.data.url,
      imageUrl: res.data.thumbnail_url || res.data.url,
      hdImageUrl: res.data.hdurl || res.data.url
    };

    return response.status(200).json({
      success: true,
      item: nasaImage
    });
  } catch (error) {
    console.error(`Unable to fetch the NASA image: ${error.message}`)
    return response.status(502).json({
      success: false,
      error: 'Unable to fetch the NASA image'
    });
  }
}

function isValidApodDate(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return false;
  }

  const parsedDate = new Date(`${date}T00:00:00Z`);
  const today = new Date().toISOString().slice(0, 10);

  return !Number.isNaN(parsedDate.getTime()) &&
    parsedDate.toISOString().slice(0, 10) === date &&
    date >= '1995-06-16' &&
    date <= today;
}
module.exports = {
  getImage
}
