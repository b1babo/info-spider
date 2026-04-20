# producthunt.py
from datetime import datetime, timedelta, timezone
import json
import logging
import requests
from graphene import ObjectType, String, Schema
logger = logging.getLogger(__name__)
class Product(ObjectType):
    name = String()
    tagline = String()

class Query(ObjectType):
    product = String()

def fetch_data(query, api_key,variables=None):
    url = 'https://api.producthunt.com/v2/api/graphql'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    if variables:
      response = requests.post(url, headers=headers, json={'query': query,"variables":variables})
    else:
        response = requests.post(url, headers=headers, json={'query': query})
    return response.json()

class ProductHunt:
    def __init__(self, api_key):
        self.api_key = api_key




    def query_posts_data(self,cursor=None,per_page=10,date_from:datetime = datetime.now(timezone.utc), date_to:datetime = datetime.now(timezone.utc),topic=""):
        POSTS_QUERY = """
          query GetProductHuntPosts($cursor: String, $perPage: Int, $dateFrom: DateTime,$dateTo: DateTime,$topic: String!) {
            posts(first: $perPage, after: $cursor, order: NEWEST, postedAfter: $dateFrom,postedBefore: $dateTo,topic: $topic) {
              edges {
                cursor
                node {
                  id
                  name
                  tagline
                  description
                  slug
                  url
                  votesCount
                  createdAt
                  website
                  userId

                  media {
                    type
                    url
                    videoUrl
                  }
                  
                  topics(first: 5) {
                    edges { node { name url id slug} }
                  }

                  makers {
                    headline
                    name
                    username
                    id
                    url
                  }
                  
                  comments(first: 5, order: VOTES_COUNT) {
                    edges {
                      node {
                        parentId
                        userId
                        id
                        body
                        votesCount
                        url
                        user { name username }
                      }
                    }
                  }
                }
                
              }
              
              pageInfo {
                hasNextPage
                endCursor
              }
            }
          }
          """


        
        date_from_str = date_from.strftime("%Y-%m-%dT%H:%M:%SZ")
        date_to_str = date_to.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"{date_from_str} => {date_to_str}")
        variables = {
                            "cursor": cursor,
                            "perPage": per_page,
                            "dateFrom": date_from_str, # 传入时间参数
                            "dateTo":date_to_str,
                            "topic" : topic
                            
                        }

        data = fetch_data(POSTS_QUERY, self.api_key,variables=variables)
        products = data.get('data', {}).get('posts', {}).get('edges', [])
        # logger.info(f"products {data}")
        product_list = []
        for edge in products:
            product = edge.get('node', {})
            product_list.append(product)
        
        return product_list

    def query_user_data(self,user_id):
      USER_QUERY = """
          query GetProductHuntUser($id: ID!) {
            user(id: $id) {
              id
              name
              username
              url
              # profileImage(size: 100)
              headline
            }
          }
          """
      variables = {"id": user_id}    
      data = fetch_data(USER_QUERY, self.api_key,variables=variables)
      # logger.info(f"user {data}")

      user = data.get('data', {}).get('user', {})
      return user



    def query_topics_by_topic(self, cursor=None,per_page=10,query=""):
        


      TOPICS_QUERY = """
          query GetProductHuntTopics($cursor: String, $perPage: Int, $query: String!) {
            topics(first: $perPage, after: $cursor, order: FOLLOWERS_COUNT,query:$query ) {
              edges { 
                node { 
                  name 
                  url 
                  id 
                  slug
                } 
              }
            }
          }
          """

      variables = {
                    "cursor": cursor,
                    "perPage": per_page,
                    "query" : query
                      }

      data = fetch_data(TOPICS_QUERY, self.api_key,variables=variables)
      
      topics = data.get('data', {}).get('topics', {}).get('edges', [])
      # logger.info(f"topics {topics}")
      

      topic_list = []
      for edge in topics:
          topic = edge.get('node', {})
          topic_list.append(topic)


      return topic_list




if __name__ == "__main__":
    p = ProductHunt(api_key="OovEfBdnMo9gwumYXKHDGDYxG34rT0pXjOeoCbf3kzs")
    # ret = p.get_daily()
    # print("ret ",ret)
    print(p.query_user_data("8774692"))

    print(p.query_topics_by_topic(query="saas"))